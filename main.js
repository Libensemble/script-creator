const templatePaths = { 
  run: 'templates/run_libe.py.j2', 
  simf: 'templates/simf.py.j2',
  batch_slurm: 'templates/submit_slurm.sh.j2',
  batch_pbs: 'templates/submit_pbs.sh.j2'
};
let generatorSpecs = {};
fetch("data/generator_specs.json").then(res => res.json()).then(data => { generatorSpecs = data; });
const GEN_TO_ALLOC = {
  "aposmm": {
    alloc_module: "persistent_aposmm_alloc",
    alloc_function: "persistent_aposmm_alloc",
    alloc_specs_user: ""
  },
  "default": {
    alloc_module: "start_only_persistent",
    alloc_function: "only_persistent_gens",
    alloc_specs_user: 'user={"async_return": False},'
  }
};

// Keep only setupTemplateVarButtons global since it needs to be called from loadFormData
function setupTemplateVarButtons() {
  document.querySelectorAll('.template-var-row').forEach((row, idx, rows) => {
    // Remove all buttons
    row.querySelectorAll('button').forEach(btn => btn.remove());
    // Add + to last row only
    if (idx === rows.length - 1) {
      const addBtn = document.createElement('button');
      addBtn.type = 'button';
      addBtn.className = 'add-var-btn';
      addBtn.style.marginLeft = '5px';
      addBtn.textContent = '+';
      addBtn.onclick = function() {
        const container = document.getElementById('templateVars');
        const newRow = document.createElement('div');
        newRow.className = 'template-var-row';
        newRow.innerHTML = `<input name="template_var" placeholder="variable name" style="width: 200px; display: inline-block;">`;
        container.appendChild(newRow);
        setupTemplateVarButtons();
      };
      row.appendChild(addBtn);
    }
    // Add - to all rows except the first
    if (rows.length > 1 && idx > 0) {
      const removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'remove-var-btn';
      removeBtn.style.marginLeft = '5px';
      removeBtn.textContent = '-';
      removeBtn.onclick = function() {
        row.remove();
        setupTemplateVarButtons();
      };
      row.appendChild(removeBtn);
    }
  });
}

async function fetchTemplates(clusterEnabled, schedulerType) {
  const ts = Date.now();
  const promises = [
    fetch(`${templatePaths.run}?_=${ts}`).then(r => r.text()),
    fetch(`${templatePaths.simf}?_=${ts}`).then(r => r.text())
  ];
  
  let batchTpl = null;
  if (clusterEnabled && schedulerType) {
    const batchPath = schedulerType === 'slurm' ? templatePaths.batch_slurm : templatePaths.batch_pbs;
    promises.push(fetch(`${batchPath}?_=${ts}`).then(r => r.text()));
  }
  
  const results = await Promise.all(promises);
  return { 
    runTpl: results[0], 
    simfTpl: results[1], 
    batchTpl: results[2] || null 
  };
}

fetch("data/generators.json").then(res => res.json()).then(data => {
  const modSel = document.getElementById("gen_module"), funcSel = document.getElementById("gen_function");
  Object.keys(data).forEach(mod => {
    const option = new Option(mod, mod);
    option.title = data[mod].description;  // Add tooltip
    modSel.add(option);
  });
  modSel.onchange = () => {
    funcSel.innerHTML = "";
    data[modSel.value].generators.forEach(f => funcSel.add(new Option(f, f)));
  };
  modSel.onchange();
});
document.getElementById("layoutSideBySide").onclick = function() {
  document.getElementById("outputLayout").className = "output-columns";
  this.classList.add("active"); document.getElementById("layoutStacked").classList.remove("active");
};
document.getElementById("layoutStacked").onclick = function() {
  document.getElementById("outputLayout").className = "output-stack";
  this.classList.add("active"); document.getElementById("layoutSideBySide").classList.remove("active");
};
document.getElementById('scriptForm').onsubmit = async function(e) {
  e.preventDefault();
  document.getElementById('customizeText').style.display = 'block';
  const form = e.target, data = {};
  // --- Ensure set_objective_code is never empty if customizing ---
  const customSetObjective = document.getElementById('customSetObjective').checked;
  const setObjectiveEditor = document.getElementById('setObjectiveEditor');
  if (customSetObjective && setObjectiveEditor.value.trim() === '') {
    // Build data object for default code
    const tempData = {};
    for (const [k,v] of new FormData(form).entries()) {
      tempData[k] = v;
    }
    setObjectiveEditor.value = getDefaultSetObjectiveCode(tempData);
  }
  // --- End ensure ---
  for (const [k,v] of new FormData(form).entries()) {
    if (k === 'nodes' || k === 'procs') {
      if (v.trim() !== '' && v !== '0') {
        const numValue = parseInt(v, 10);
        if (numValue <= 0) {
          alert(`Number of ${k === 'nodes' ? 'Nodes' : 'Procs'} must be greater than 0 (or leave empty/0 for Auto)`);
          return;
        }
        data[k] = numValue;
      }
    } else {
      data[k] = v;
    }
  }
  // Set dimension, lb_array, ub_array before rendering customGenSpecsStr
  data.dimension = parseInt(form.dimension.value);
  data.lb_array = 'np.array([' + Array(data.dimension).fill(0.0).join(', ') + '])';
  data.ub_array = 'np.array([' + Array(data.dimension).fill(3.0).join(', ') + '])';
  // --- Custom gen_specs logic ---
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
  // Pretty-print GenSpecs arguments for Python

  let customGenSpecsStr = null;
  if (customSpec) {
    if (typeof customSpec === 'string') {
      customGenSpecsStr = customSpec;
    } else {
      customGenSpecsStr = prettyPrintPythonArgs(customSpec);
    }
  }
  data.custom_gen_specs = customGenSpecsStr ? Mustache.render(customGenSpecsStr, data) : null;
  // --- End custom gen_specs logic ---
  const rawGpus = form.gpus.value.trim();
  data.auto_gpus = document.getElementById('autoGpus').checked;
  data.num_gpus = rawGpus === "" ? 0 : parseInt(rawGpus);
  data.gpus_line = (!data.auto_gpus && data.num_gpus > 0) ? `num_gpus=${data.num_gpus},` : "";
  data.needs_mpich_gpu_support = data.auto_gpus || data.num_gpus > 0;

  // Cluster logic
  data.cluster_enabled = form.cluster_enable.checked;
  data.cluster_total_nodes = data.cluster_enabled ? form.cluster_total_nodes.value : null;
  data.scheduler_type = data.cluster_enabled ? form.scheduler_type.value : null;
  data.total_nodes = data.cluster_total_nodes; // For template compatibility
  
  // Input handling logic
  data.input_type = form.input_type.value;
  data.input_path = form.input_path.value;
  data.templated_enabled = form.templated_enable.checked;
  data.templated_filename = data.templated_enabled ? form.templated_filename.value : null;
  data.input_usage = form.input_usage.value;
  data.input_usage_cmdline = (data.input_usage === "cmdline");
  
  // Collect template variables
  const templateVarInputs = form.querySelectorAll('input[name="template_var"]');
  const templateVars = Array.from(templateVarInputs)
    .map(input => input.value.trim())
    .filter(val => val !== '');
  data.template_vars = templateVars;
  
  // Set template data based on input type and templated settings
  if (data.input_type === 'file') {
    data.input_file = data.input_path;
    data.input_file_basename = data.input_path.split(/[\\/]/).pop();
    data.sim_input_dir = null;
    data.templated_filename = null;
  } else {
    data.input_file = null;
    data.input_file_basename = null;
    data.sim_input_dir = data.input_path;
    data.templated_filename = form.templated_filename.value;
  }
  
  // Template variables for user section
  if (data.templated_enabled && templateVars.length > 0) {
    data.has_template_vars = true;
    data.template_vars_list = templateVars.map(v => `"${v}"`).join(', ');
  } else {
    data.has_template_vars = false;
    data.template_vars_list = '';
  }
  
  let allocInfo;
  if (data.gen_function && data.gen_function.toLowerCase().includes("aposmm")) {
    allocInfo = GEN_TO_ALLOC["aposmm"];
  } else {
    allocInfo = GEN_TO_ALLOC["default"];
  }
  data.alloc_module = allocInfo.alloc_module;
  data.alloc_function = allocInfo.alloc_function;
  data.alloc_specs_user = allocInfo.alloc_specs_user;
  
  // Set set_objective_code just before rendering templates, to ensure it is always present
  if (document.getElementById('customSetObjective').checked) {
    data.set_objective_code = document.getElementById('setObjectiveEditor').value;
  } else {
    data.set_objective_code = getDefaultSetObjectiveCode(data);
  }
  const { runTpl, simfTpl, batchTpl } = await fetchTemplates(data.cluster_enabled, data.scheduler_type);
  Mustache.escape=text=>text;
  const runRendered = Mustache.render(runTpl,data);
  const simfRendered = Mustache.render(simfTpl,data);
  let batchRendered = null;
  
  if (data.cluster_enabled && batchTpl) {
    batchRendered = Mustache.render(batchTpl, data);
    const batchFilename = data.scheduler_type === 'slurm' ? 'submit_slurm.sh' : 'submit_pbs.sh';
    document.getElementById('batchFilename').textContent = `${batchFilename}:`;
    document.getElementById('batchLink').download = batchFilename;
    document.getElementById('batchColumn').style.display = '';
    updateCodeBlock('batchScript', batchRendered);
    document.getElementById('batchLink').href=URL.createObjectURL(new Blob([batchRendered],{type:'text/x-shellscript'}));
  } else {
    document.getElementById('batchColumn').style.display = 'none';
  }
  
  function updateCodeBlock(id, code) {
    const pre = document.getElementById(id).parentElement;
    const language = id === 'batchScript' ? 'language-bash' : 'language-python';
    pre.innerHTML = `<button type="button" class="copy-btn" data-copytarget="${id}" title="Copy"><svg viewBox="0 0 24 24" fill="none"><rect x="5" y="9" width="10" height="10" rx="2" stroke="currentColor" stroke-width="1.5"/><rect x="9" y="5" width="10" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="1.5"/></svg></button><code id="${id}" class="${language}"></code>`;
    const newCode = document.getElementById(id);
    newCode.textContent = code;
    hljs.highlightElement(newCode);
    setupCopyIcons();
  }
  updateCodeBlock('runScript', runRendered);
  updateCodeBlock('simfScript', simfRendered);
  document.getElementById('output').style.display='block';
  document.getElementById('runLink').href=URL.createObjectURL(new Blob([runRendered],{type:'text/x-python'}));
  document.getElementById('simfLink').href=URL.createObjectURL(new Blob([simfRendered],{type:'text/x-python'}));
  document.getElementById('zipLink').onclick=function(){
    const zip=new JSZip(); 
    zip.file("run_libe.py",runRendered); 
    zip.file("simf.py",simfRendered);
    if (batchRendered) {
      const batchFilename = data.scheduler_type === 'slurm' ? 'submit_slurm.sh' : 'submit_pbs.sh';
      zip.file(batchFilename, batchRendered);
    }
    zip.generateAsync({type:"blob"}).then(content=>saveAs(content,"scripts.zip"));
  };
  // Clipboard copy logic for all scripts (icon in code block)
  function setupCopyIcons() {
    document.querySelectorAll('.copy-btn').forEach(btn => {
      btn.onclick = async function(e) {
        e.stopPropagation();
        const codeId = btn.getAttribute('data-copytarget');
        const code = document.getElementById(codeId).textContent;
        try {
          await navigator.clipboard.writeText(code);
          btn.classList.add('copied');
          btn.title = 'Copied!';
          setTimeout(() => { btn.classList.remove('copied'); btn.title = 'Copy'; }, 1200);
        } catch (e) {
          btn.title = 'Error';
          setTimeout(() => { btn.title = 'Copy'; }, 1200);
        }
      };
    });
  }
  document.addEventListener('DOMContentLoaded', setupCopyIcons);
  // Also re-setup copy icons after scripts are generated (in case of rerender)
  setupCopyIcons();
  // --- Output Parsing Custom set_objective_value() logic ---
  let isCustomSetObjective = false;
  let lastDefaultSetObjectiveCode = '';

  function getDefaultSetObjectiveCode(data) {
    return `def set_objective_value():\n    try:\n        data = np.loadtxt(\"${data.app_ref || ''}.stat\")\n        return data[-1]\n    except Exception:\n        return np.nan`;
  }

  function updateSetObjectiveEditor(defaultCode) {
    const editor = document.getElementById('setObjectiveEditor');
    if (editor.value.trim() === '') {
      editor.value = defaultCode;
    }
    lastDefaultSetObjectiveCode = defaultCode;
  }

  function setCustomizeEditorVisibility() {
    isCustomSetObjective = document.getElementById('customSetObjective').checked;
    const container = document.getElementById('setObjectiveEditorContainer');
    const editor = document.getElementById('setObjectiveEditor');
    if (isCustomSetObjective) {
      container.style.display = '';
      // Pre-fill with default code if empty
      const form = document.getElementById('scriptForm');
      const data = {};
      for (const [k,v] of new FormData(form).entries()) {
        data[k] = v;
      }
      const defaultCode = getDefaultSetObjectiveCode(data);
      if (editor.value.trim() === '') {
        editor.value = defaultCode;
      }
      editor.disabled = false;
    } else {
      container.style.display = 'none';
    }
  }

  document.getElementById('customSetObjective').addEventListener('change', function() {
    setCustomizeEditorVisibility();
  });
  // Ensure visibility is set immediately after attaching the event listener
  setCustomizeEditorVisibility();

  // On form changes, update the set_objective code if customizing and the box is empty
  function updateSetObjectiveFromForm() {
    if (!isCustomSetObjective) return;
    const form = document.getElementById('scriptForm');
    const data = {};
    for (const [k,v] of new FormData(form).entries()) {
      data[k] = v;
    }
    const defaultCode = getDefaultSetObjectiveCode(data);
    updateSetObjectiveEditor(defaultCode);
  }

  // Initial set on DOMContentLoaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
      setCustomizeEditorVisibility();
      updateSetObjectiveFromForm();
    });
  } else {
    setCustomizeEditorVisibility();
    updateSetObjectiveFromForm();
  }
};
document.getElementById("fillBtn").onclick = function() {
    const f = document.forms[0];
    f.elements["app_ref"].value = "warpx";
    f.elements["num_workers"].value = "4";
    f.elements["sim_app"].value = "/home/user/warpx.x";
    f.elements["input_path"].value = "/user/home/warpx_input";
    f.elements["max_sims"].value = "8";
    f.elements["nodes"].value = "";
    f.elements["procs"].value = "8";
    f.elements["gpus"].value = 0;
    document.getElementById("autoGpus").checked = false;
    document.getElementById("gpusInput").disabled = false;
    document.querySelector('input[name="procs"]').disabled = false;
    const modSel = document.getElementById("gen_module");
    const funcSel = document.getElementById("gen_function");
    modSel.selectedIndex = 0;
    modSel.dispatchEvent(new Event("change"));
    setTimeout(() => {
      if (funcSel.options.length > 0) funcSel.selectedIndex = 0;
    }, 50);
  };
// Cluster section show/hide logic
document.addEventListener('DOMContentLoaded', function() {
  const clusterEnable = document.getElementById('clusterEnable');
  const clusterFields = document.getElementById('clusterFields');
  if (clusterEnable) {
    clusterEnable.addEventListener('change', function() {
      clusterFields.style.display = this.checked ? '' : 'none';
    });
    // Set initial state on page load
    clusterFields.style.display = clusterEnable.checked ? '' : 'none';
  }
});
// Template variables management
document.addEventListener('DOMContentLoaded', function() {
  // Input type change handler
  const inputTypeRadios = document.querySelectorAll('input[name="input_type"]');
  const inputPathLabelText = document.getElementById('inputPathLabelText');
  const templatedFileLabel = document.getElementById('templatedFileLabel');
  
  function updateInputLabels() {
    const isDirectory = document.querySelector('input[name="input_type"]:checked').value === 'directory';
    inputPathLabelText.textContent = isDirectory ? 'Input Directory:' : 'Input File Path:';
    // Only show Template Filename if both Directory and Templated are selected
    const templatedChecked = document.getElementById('templatedEnable').checked;
    templatedFileLabel.style.display = (isDirectory && templatedChecked) ? '' : 'none';
  }
  
  inputTypeRadios.forEach(radio => {
    radio.addEventListener('change', updateInputLabels);
  });
  
  // Templated checkbox handler
  const templatedEnable = document.getElementById('templatedEnable');
  const templatedFields = document.getElementById('templatedFields');
  templatedEnable.addEventListener('change', function() {
    templatedFields.style.display = this.checked ? '' : 'none';
    updateInputLabels(); // Also update template file label visibility
  });
  
  // Template variable add/remove functionality
  setupTemplateVarButtons();
});
document.addEventListener('DOMContentLoaded', function() {
  // Tooltip for Templated label
  const tooltipLabel = document.getElementById('templatedTooltipLabel');
  const tooltip = document.getElementById('templatedTooltip');
  if (tooltipLabel && tooltip) {
    tooltipLabel.addEventListener('mouseenter', function() {
      tooltip.style.display = 'block';
    });
    tooltipLabel.addEventListener('mouseleave', function() {
      tooltip.style.display = 'none';
    });
    // Also show tooltip when focusing the checkbox (for accessibility)
    const templatedCheckbox = document.getElementById('templatedEnable');
    templatedCheckbox.addEventListener('focus', function() {
      tooltip.style.display = 'block';
    });
    templatedCheckbox.addEventListener('blur', function() {
      tooltip.style.display = 'none';
    });
  }
});
document.addEventListener('DOMContentLoaded', function() {
  // Auto GPU logic
  const autoGpus = document.getElementById('autoGpus');
  const gpusInput = document.getElementById('gpusInput');
  const nodesInput = document.querySelector('input[name="nodes"]');
  const procsInput = document.querySelector('input[name="procs"]');
  const autoGpusTooltipLabel = autoGpus?.parentElement;
  const autoGpusTooltip = document.getElementById('autoGpusTooltip');
  
  if (autoGpusTooltipLabel && autoGpusTooltip) {
    autoGpusTooltipLabel.addEventListener('mouseenter', function() {
      autoGpusTooltip.style.display = 'block';
    });
    autoGpusTooltipLabel.addEventListener('mouseleave', function() {
      autoGpusTooltip.style.display = 'none';
    });
    autoGpus.addEventListener('focus', function() {
      autoGpusTooltip.style.display = 'block';
    });
    autoGpus.addEventListener('blur', function() {
      autoGpusTooltip.style.display = 'none';
    });
  }
  
  function setResourceFieldsDisabled(disabled) {
    gpusInput.disabled = disabled;
    nodesInput.disabled = disabled;
    procsInput.disabled = disabled;
  }
  
  if (autoGpus && gpusInput && nodesInput && procsInput) {
    autoGpus.addEventListener('change', function() {
      setResourceFieldsDisabled(this.checked);
    });
    // Set initial state on page load
    setResourceFieldsDisabled(autoGpus.checked);
  }
  
  // Add validation for nodes input
  if (nodesInput) {
    nodesInput.addEventListener('input', function(e) {
      const value = e.target.value.trim();
      if (value === '0') {
        e.target.value = '';
      } else if (value !== '') {
        const numValue = parseInt(value, 10);
        if (numValue <= 0) {
          e.target.value = '';
        }
      }
    });

    // Handle up/down arrows
    nodesInput.addEventListener('keydown', function(e) {
      if (e.key === 'ArrowDown') {
        const value = e.target.value.trim();
        if (value === '1') {
          e.preventDefault();
          e.target.value = '';
        }
      } else if (e.key === 'ArrowUp') {
        const value = e.target.value.trim();
        if (value === '') {
          e.preventDefault();
          e.target.value = '1';
        }
      }
    });
  }

  // Add same validation for procs input
  if (procsInput) {
    procsInput.addEventListener('input', function(e) {
      const value = e.target.value.trim();
      if (value === '0') {
        e.target.value = '';
      } else if (value !== '') {
        const numValue = parseInt(value, 10);
        if (numValue <= 0) {
          e.target.value = '';
        }
      }
    });

    // Handle up/down arrows
    procsInput.addEventListener('keydown', function(e) {
      if (e.key === 'ArrowDown') {
        const value = e.target.value.trim();
        if (value === '1') {
          e.preventDefault();
          e.target.value = '';
        }
      } else if (e.key === 'ArrowUp') {
        const value = e.target.value.trim();
        if (value === '') {
          e.preventDefault();
          e.target.value = '1';
        }
      }
    });
  }
});
// --- Subtle Load/Save dropdown logic ---
(function() {
  const btn = document.getElementById('devLoadSaveBtn');
  const menu = document.getElementById('devLoadSaveMenu');
  let menuOpen = false;
  btn.onclick = function(e) {
    e.stopPropagation();
    menu.style.display = menuOpen ? 'none' : 'block';
    menuOpen = !menuOpen;
  };
  // Hide menu when clicking outside
  document.addEventListener('click', function(e) {
    if (menuOpen && !menu.contains(e.target) && e.target !== btn) {
      menu.style.display = 'none';
      menuOpen = false;
    }
  });
})();
// --- Save/Load/Delete Entry logic ---
function getSavedEntryNames() {
  return Object.keys(localStorage)
    .filter(k => k.startsWith('libeFormData:'))
    .map(k => k.replace('libeFormData:', ''));
}
function updateSavedEntriesDropdown() {
  const dropdown = document.getElementById('savedEntriesDropdown');
  const names = getSavedEntryNames();
  dropdown.innerHTML = '<option value="">-- Select Saved Entry --</option>' +
    names.map(name => `<option value="${name}">${name}</option>`).join('');
}
function saveFormData() {
  const name = prompt('Enter a name for this save:');
  if (!name) return;
  const form = document.getElementById('scriptForm');
  const data = {};
  for (const [k, v] of new FormData(form).entries()) {
    data[k] = v;
  }
  // Save checkbox/radio states
  form.querySelectorAll('input[type="checkbox"]').forEach(cb => {
    data[cb.name] = cb.checked;
  });
  form.querySelectorAll('input[type="radio"]:checked').forEach(rb => {
    data[rb.name] = rb.value;
  });
  // Save template vars
  const templateVarInputs = form.querySelectorAll('input[name="template_var"]');
  data.template_vars = Array.from(templateVarInputs).map(input => input.value);
  // Save set_objective_code
  const setObj = document.getElementById('setObjectiveEditor');
  if (setObj) data.set_objective_code = setObj.value;
  localStorage.setItem('libeFormData:' + name, JSON.stringify(data));
  updateSavedEntriesDropdown();
  alert('Saved as "' + name + '"');
}
function loadFormData() {
  const dropdown = document.getElementById('savedEntriesDropdown');
  const name = dropdown.value;
  if (!name) { alert('Select a saved entry to load.'); return; }
  const data = JSON.parse(localStorage.getItem('libeFormData:' + name) || '{}');
  const form = document.getElementById('scriptForm');
  
  for (const [k, v] of Object.entries(data)) {
    if (form.elements[k]) {
      if (form.elements[k].type === 'checkbox') {
        form.elements[k].checked = !!v;
      } else if (form.elements[k].type === 'radio') {
        const radios = form.querySelectorAll(`input[name="${k}"]`);
        radios.forEach(rb => { rb.checked = (rb.value === v); });
      } else {
        form.elements[k].value = v;
      }
    }
  }
  
  // Restore template vars
  if (Array.isArray(data.template_vars)) {
    const container = document.getElementById('templateVars');
    container.innerHTML = '';
    data.template_vars.forEach((val, idx) => {
      const row = document.createElement('div');
      row.className = 'template-var-row';
      row.innerHTML = `<input name="template_var" placeholder="variable name" style="width: 200px; display: inline-block;" value="${val}">`;
      container.appendChild(row);
    });
    // Always at least one row
    if (data.template_vars.length === 0) {
      const row = document.createElement('div');
      row.className = 'template-var-row';
      row.innerHTML = `<input name="template_var" placeholder="variable name" style="width: 200px; display: inline-block;">`;
      container.appendChild(row);
    }
  }
  
  // Restore set_objective_code
  if (data.set_objective_code && document.getElementById('setObjectiveEditor')) {
    document.getElementById('setObjectiveEditor').value = data.set_objective_code;
  }
  
  // Ensure templated fields are shown/hidden correctly after loading
  const templatedEnable = document.getElementById('templatedEnable');
  const templatedFields = document.getElementById('templatedFields');
  if (templatedEnable && templatedFields) {
    templatedFields.style.display = templatedEnable.checked ? '' : 'none';
  }
  
  // Trigger all the necessary events to update UI properly
  // Generator dropdowns
  const modSel = document.getElementById("gen_module");
  if (modSel && modSel.onchange) {
    modSel.onchange(); // This populates the function dropdown
    // Set function value after dropdown is populated
    if (data.gen_function) {
      setTimeout(() => {
        const funcSel = document.getElementById('gen_function');
        if (funcSel) funcSel.value = data.gen_function;
      }, 10);
    }
  }
  
  // Trigger change events for UI updates
  document.querySelectorAll('input[type="radio"], input[type="checkbox"], select').forEach(el => {
    el.dispatchEvent(new Event('change', { bubbles: true }));
  });
  
  setupTemplateVarButtons();
  alert('Loaded "' + name + '"');
}
function deleteFormData() {
  const dropdown = document.getElementById('savedEntriesDropdown');
  const name = dropdown.value;
  if (!name) { alert('Select a saved entry to delete.'); return; }
  if (!confirm('Delete saved entry "' + name + '"?')) return;
  localStorage.removeItem('libeFormData:' + name);
  updateSavedEntriesDropdown();
  alert('Deleted "' + name + '"');
}
document.getElementById('saveEntryBtn').onclick = saveFormData;
document.getElementById('loadEntryBtn').onclick = loadFormData;
document.getElementById('deleteEntryBtn').onclick = deleteFormData;
document.addEventListener('DOMContentLoaded', updateSavedEntriesDropdown);
document.addEventListener('DOMContentLoaded', function() {
  const dirBtn = document.getElementById('inputUsageDir');
  const cmdBtn = document.getElementById('inputUsageCmd');
  if (dirBtn && cmdBtn) {
    dirBtn.onclick = function() {
      dirBtn.classList.add('active');
      cmdBtn.classList.remove('active');
      dirBtn.querySelector('input').checked = true;
      cmdBtn.querySelector('input').checked = false;
    };
    cmdBtn.onclick = function() {
      cmdBtn.classList.add('active');
      dirBtn.classList.remove('active');
      cmdBtn.querySelector('input').checked = true;
      dirBtn.querySelector('input').checked = false;
    };
  }
});
