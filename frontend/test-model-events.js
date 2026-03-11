// TEST SCRIPT - Run in browser console at http://localhost:3000/resume?rt_debug=1
//
// This tests if model selection events are being dispatched correctly

console.log('=== MODEL SELECTION EVENT TEST ===');

// Listen for rt-sidebar events
window.addEventListener('rt-sidebar', (e) => {
  const d = e.detail || {};
  console.log('✅ rt-sidebar event received:', {
    fitModelLabel: d.fitModelLabel,
    tailorModelLabel: d.tailorModelLabel,
    judgeLabel: d.judgeLabel
  });
});

// Listen for rt-multi-models events
window.addEventListener('rt-multi-models', (e) => {
  const d = e.detail || {};
  console.log('✅ rt-multi-models event received:', {
    singleFit: d.singleFit,
    singleTailor: d.singleTailor,
    singleJudge: d.singleJudge,
    multiMode: d.multiMode
  });
});

console.log('Event listeners installed. Now:');
console.log('1. Select a model in the sidebar');
console.log('2. Watch for event logs above');
console.log('3. Check if fitModelLabel contains full label (with em-dash and description)');
console.log('4. Try clicking "Check Fit" button to see validation message');
