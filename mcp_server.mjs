#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { readFileSync } from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { createRequire } from "module";

const require = createRequire(import.meta.url);
const Mustache = require("mustache");
const __dirname = path.dirname(fileURLToPath(import.meta.url));

const server = new Server(
  {
    name: "script-creator",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// List available tools
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "CreateLibEnsembleScripts",
        description: "Render script using existing script-creator templates",
        inputSchema: {
          type: "object",
          properties: {
            app_ref: { type: "string", description: "Application reference name" },
            num_workers: { type: "string", description: "Number of workers" },
            sim_app: { type: "string", description: "Path to simulation application" },
            input_path: { type: "string", description: "Path to input file or directory" },
            dimension: { type: "string", description: "Number of parameters" },
            max_sims: { type: "string", description: "Maximum simulations" },
            input_type: { type: "string", description: "Input type: file or directory" },
            templated_enable: { type: "boolean", description: "Enable templated input file" },
            templated_filename: { type: "string", description: "Template filename" },
            template_vars: { type: "array", description: "Template variable names", items: { type: "string" } },
            cluster_enable: { type: "boolean", description: "Enable cluster mode" },
            cluster_total_nodes: { type: "string", description: "Total nodes for cluster" },
            scheduler_type: { type: "string", description: "Scheduler type (slurm or pbs)" },
            gen_module: { type: "string", description: "Generator module" },
            gen_function: { type: "string", description: "Generator function" },
            nodes: { type: "string", description: "Number of nodes" },
            procs: { type: "string", description: "Number of processes" },
            gpus: { type: "string", description: "Number of GPUs" },
            input_usage: { type: "string", description: "Input usage: directory or cmdline" },
            custom_set_objective: { type: "boolean", description: "Use custom set_objective function" },
            set_objective_code: { type: "string", description: "Custom set_objective_value() function code" },
          },
          additionalProperties: true,
        },
      },
    ],
  };
});

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  if (request.params.name !== "CreateLibEnsembleScripts") {
    throw new Error(`Unknown tool: ${request.params.name}`);
  }

  const params = request.params.arguments || {};
  
  try {
    // Process parameters similar to main.js
    const data = { ...params };
    
    // Set dimension-based arrays
    data.dimension = parseInt(data.dimension || 2);
    data.lb_array = 'np.array([' + Array(data.dimension).fill(0.0).join(', ') + '])';
    data.ub_array = 'np.array([' + Array(data.dimension).fill(3.0).join(', ') + '])';
    
    // GPU settings
    data.auto_gpus = data.auto_gpus || false;
    data.num_gpus = parseInt(data.gpus || 0);
    data.gpus_line = (!data.auto_gpus && data.num_gpus > 0) ? `num_gpus=${data.num_gpus},` : "";
    data.needs_mpich_gpu_support = data.auto_gpus || data.num_gpus > 0;
    
    // Cluster settings
    data.cluster_enabled = data.cluster_enable || false;
    data.total_nodes = data.cluster_total_nodes || data.total_nodes || 1;
    data.scheduler_type = data.scheduler_type || 'slurm';
    
    // Input handling
    data.input_type = data.input_type || 'file';
    data.input_usage = data.input_usage || 'directory';
    data.input_usage_cmdline = (data.input_usage === "cmdline");
    
    // Set template data based on input type and templated settings
    if (data.input_type === 'file') {
      data.input_file = data.input_path;
      data.input_file_basename = data.input_path ? data.input_path.split(/[\\/]/).pop() : null;
      data.sim_input_dir = null;
      data.templated_filename = null;
    } else {
      data.input_file = null;
      data.input_file_basename = null;
      data.sim_input_dir = data.input_path;
      data.templated_filename = data.templated_filename || null;
    }
    
    // Determine input_filename for user/app_args
    const templateVars = Array.isArray(data.template_vars) ? data.template_vars : [];
    const inputFilename = (() => {
      if (data.input_type === 'file' && data.input_path) {
        return data.input_path.split(/[\\/]/).pop();
      } else if (data.input_type === 'directory' && data.templated_enable && data.templated_filename) {
        return data.templated_filename;
      }
      return '';
    })();
    
    // Set input_filename when "in command line" is selected OR when there are templated values
    const needsInputFilename = (data.input_usage === 'cmdline') || (data.templated_enable && templateVars.length > 0);
    if (needsInputFilename && inputFilename) {
      data.input_filename = inputFilename;
    } else {
      delete data.input_filename;
    }
    
    // Only set input_names if there are templated values
    if (data.templated_enable && templateVars.length > 0) {
      data.has_template_vars = true;
      data.template_vars_list = templateVars.map(v => `"${v}"`).join(', ');
      data.input_names = templateVars;
      data.has_input_names = true;
    } else {
      data.has_template_vars = false;
      data.template_vars_list = '';
      delete data.input_names;
      data.has_input_names = false;
    }
    
    // Allocation settings
    const genFunc = (data.gen_function || '').toLowerCase();
    if (genFunc.includes('aposmm')) {
      data.alloc_module = 'persistent_aposmm_alloc';
      data.alloc_function = 'persistent_aposmm_alloc';
      data.alloc_specs_user = '';
    } else {
      data.alloc_module = 'start_only_persistent';
      data.alloc_function = 'only_persistent_gens';
      data.alloc_specs_user = 'user={"async_return": True},';
    }
    
    // Set default objective code
    if (!data.set_objective_code) {
      data.set_objective_code = `def set_objective_value():
    try:
        data = np.loadtxt("${data.app_ref || ''}.stat")
        return data[-1]
    except Exception:
        return np.nan`;
    }
    
    // Load templates
    const runTpl = readFileSync(path.join(__dirname, 'templates/run_libe.py.j2'), 'utf8');
    const simfTpl = readFileSync(path.join(__dirname, 'templates/simf.py.j2'), 'utf8');
    
    // Disable HTML escaping for Mustache
    Mustache.escape = text => text;
    
    // Render templates
    const runRendered = Mustache.render(runTpl, data);
    const simfRendered = Mustache.render(simfTpl, data);
    
    let output = `=== run_libe.py ===\n${runRendered}\n\n=== simf.py ===\n${simfRendered}`;
    
    // Render batch script if cluster is enabled
    if (data.cluster_enabled) {
      const batchPath = data.scheduler_type === 'slurm' 
        ? 'templates/submit_slurm.sh.j2' 
        : 'templates/submit_pbs.sh.j2';
      const batchTpl = readFileSync(path.join(__dirname, batchPath), 'utf8');
      const batchRendered = Mustache.render(batchTpl, data);
      const batchFilename = data.scheduler_type === 'slurm' ? 'submit_slurm.sh' : 'submit_pbs.sh';
      output += `\n\n=== ${batchFilename} ===\n${batchRendered}`;
    }
    
    return {
      content: [
        {
          type: "text",
          text: output,
        },
      ],
    };
  } catch (error) {
    return {
      content: [
        {
          type: "text",
          text: `Error rendering templates: ${error.message}`,
        },
      ],
      isError: true,
    };
  }
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("Script Creator MCP server running on stdio");
}

main().catch((error) => {
  console.error("Server error:", error);
  process.exit(1);
});
