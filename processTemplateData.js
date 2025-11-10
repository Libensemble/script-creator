// Shared logic for processing template data
// Works in both browser (main.js) and Node.js (mcp_server.mjs)

const GEN_TO_ALLOC = {
  "aposmm": {
    alloc_module: "persistent_aposmm_alloc",
    alloc_function: "persistent_aposmm_alloc",
    alloc_specs_user: ""
  },
  "default": {
    alloc_module: "start_only_persistent",
    alloc_function: "only_persistent_gens",
    alloc_specs_user: 'user={"async_return": True},'
  }
};

function processTemplateData(data, generatorSpecs = {}) {
  // Set dimension, lb_array, ub_array
  data.dimension = parseInt(data.dimension || 2);
  data.lb_array = 'np.array([' + Array(data.dimension).fill(0.0).join(', ') + '])';
  data.ub_array = 'np.array([' + Array(data.dimension).fill(3.0).join(', ') + '])';
  
  // Custom gen_specs logic
  const genModule = (data.gen_module || '').toLowerCase().trim();
  const genFunc = (data.gen_function || '').toLowerCase().trim();
  const combinedKey = genModule + '.' + genFunc;
  let customSpec = null;
  // Try direct match (case-insensitive, trimmed)
  for (const key in generatorSpecs) {
    if (key.toLowerCase().trim() === combinedKey) {
      customSpec = generatorSpecs[key];
      break;
    }
  }
  
  // Note: customGenSpecsStr rendering would need Mustache, handled separately
  // This function just identifies if custom spec exists
  data._custom_spec = customSpec;
  
  // GPU settings
  data.auto_gpus = data.auto_gpus || false;
  const rawGpus = data.gpus || 0;
  data.num_gpus = rawGpus === "" || rawGpus === 0 ? 0 : parseInt(rawGpus);
  data.gpus_line = (!data.auto_gpus && data.num_gpus > 0) ? `num_gpus=${data.num_gpus},` : "";
  data.needs_mpich_gpu_support = data.auto_gpus || data.num_gpus > 0;
  
  // Cluster settings
  data.cluster_enabled = data.cluster_enable || false;
  data.cluster_total_nodes = data.cluster_enabled ? (data.cluster_total_nodes || null) : null;
  data.scheduler_type = data.cluster_enabled ? (data.scheduler_type || null) : null;
  data.total_nodes = data.cluster_total_nodes; // For template compatibility
  
  // Input handling
  data.input_type = data.input_type || 'file';
  data.input_usage = data.input_usage || 'directory';
  data.input_usage_cmdline = (data.input_usage === "cmdline");
  data.templated_enabled = data.templated_enable || false;
  
  // Collect template variables (ensure it's an array)
  const templateVars = Array.isArray(data.template_vars) 
    ? data.template_vars.filter(v => v && v.trim() !== '')
    : [];
  
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
    data.templated_filename = data.templated_enabled ? (data.templated_filename || null) : null;
  }
  
  // Determine input_filename for user/app_args
  const inputFilename = (() => {
    if (data.input_type === 'file' && data.input_path) {
      return data.input_path.split(/[\\/]/).pop();
    } else if (data.input_type === 'directory' && data.templated_enabled && data.templated_filename) {
      return data.templated_filename;
    }
    return '';
  })();
  
  // Set input_filename when "in command line" is selected OR when there are templated values
  const needsInputFilename = (data.input_usage === 'cmdline') || (data.templated_enabled && templateVars.length > 0);
  if (needsInputFilename && inputFilename) {
    data.input_filename = inputFilename;
  } else {
    delete data.input_filename;
  }
  
  // Only set input_names if there are templated values
  if (data.templated_enabled && templateVars.length > 0) {
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
  if (data.gen_function && data.gen_function.toLowerCase().includes("aposmm")) {
    const allocInfo = GEN_TO_ALLOC["aposmm"];
    data.alloc_module = allocInfo.alloc_module;
    data.alloc_function = allocInfo.alloc_function;
    data.alloc_specs_user = allocInfo.alloc_specs_user;
  } else {
    const allocInfo = GEN_TO_ALLOC["default"];
    data.alloc_module = allocInfo.alloc_module;
    data.alloc_function = allocInfo.alloc_function;
    data.alloc_specs_user = allocInfo.alloc_specs_user;
  }
  
  return data;
}

function getDefaultSetObjectiveCode(data) {
  return `def set_objective_value():
    try:
        data = np.loadtxt("${data.app_ref || ''}.stat", ndmin=1)
        return data[-1]
    except Exception:
        return np.nan`;
}

// Export for Node.js
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { processTemplateData, GEN_TO_ALLOC, getDefaultSetObjectiveCode };
}

// Make available globally for browser
if (typeof window !== 'undefined') {
  window.processTemplateData = processTemplateData;
  window.GEN_TO_ALLOC = GEN_TO_ALLOC;
  window.getDefaultSetObjectiveCode = getDefaultSetObjectiveCode;
}

