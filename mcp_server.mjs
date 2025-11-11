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
const { processTemplateData, renderCustomGenSpecs, getDefaultSetObjectiveCode } = require("./processTemplateData.js");
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
            output_file_name: { type: "string", description: "Output file name to read objective from (defaults to app_ref.stat)" },
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
    // Process parameters using shared logic
    const data = { ...params };
    
    // Load generator specs
    let generatorSpecs = {};
    try {
      const generatorSpecsPath = path.join(__dirname, 'data/generator_specs.json');
      generatorSpecs = JSON.parse(readFileSync(generatorSpecsPath, 'utf8'));
    } catch (e) {
      // If file doesn't exist, use empty object
      generatorSpecs = {};
    }
    
    // Process template data using shared function
    processTemplateData(data, generatorSpecs);
    
    // Disable HTML escaping for Mustache (needed for both custom_gen_specs and template rendering)
    Mustache.escape = text => text;
    
    // Render custom gen_specs using shared function
    renderCustomGenSpecs(data, Mustache.render.bind(Mustache));
    
    // Set default objective code
    if (!data.set_objective_code) {
      data.set_objective_code = getDefaultSetObjectiveCode(data);
    }
    
    // Load templates
    const runTpl = readFileSync(path.join(__dirname, 'templates/run_libe.py.j2'), 'utf8');
    const simfTpl = readFileSync(path.join(__dirname, 'templates/simf.py.j2'), 'utf8');
    
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
