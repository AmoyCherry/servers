// ==========================================
// FILE: src/everything/cov-hook.cjs
// ==========================================
const inspector = require('inspector');
const fs = require('fs');
const path = require('path');

// Configuration
const DUMP_FILE = path.join(__dirname, 'coverage', 'runtime-dump.json');

try {
    // 1. Connect to V8 Inspector
    const session = new inspector.Session();
    session.connect();
    
    // 2. Enable Precise Coverage (Statement & Block level)
    session.post('Profiler.enable');
    session.post('Profiler.startPreciseCoverage', { 
        callCount: true, 
        detailed: true 
    });

    // Signal Python that we are ready
    console.error('[CovHook] READY');

    // // overwrite runtime-dump.json
    // 3. Listen for SIGUSR1 (The "Dump Trigger")
    // process.on('SIGUSR1', () => {
    //     session.post('Profiler.takePreciseCoverage', (err, result) => {
    //         if (err) {
    //             console.error('[CovHook] Error taking coverage:', err);
    //             return;
    //         }

    //         // 4. Filter Data (Keep only source code, ignore libraries)
    //         const meaningful = result.result.filter(script => {
    //             // Ignore node_modules
    //             if (script.url.includes('node_modules')) return false;
    //             // Keep compiled code (dist) or raw source (src)
    //             return script.url.includes('/dist/') || script.url.includes('/src/');
    //         });

    //         // 5. Write to Disk
    //         try {
    //             fs.writeFileSync(DUMP_FILE, JSON.stringify(meaningful));
    //             // Signal Python that dump is finished
    //             console.error('[CovHook] DUMP_COMPLETE'); 
    //         } catch (writeErr) {
    //             console.error('[CovHook] Write failed:', writeErr);
    //         }
    //     });
    // });

    // --- NEW METHOD: Append to trace-history.jsonl ---
    process.on('SIGUSR1', () => {
        session.post('Profiler.takePreciseCoverage', (err, result) => {
            if (err) return console.error('[CovHook] Error:', err);

            // Filter data
            const meaningful = result.result.filter(script => 
                script.url.includes('/dist/') || script.url.includes('/src/')
            );

            // --- WRITE METHOD 1: Fast Dump for Fuzzer (Overwrite) ---
            // The Python script reads this. It needs to be small and fast.
            fs.writeFileSync('coverage/runtime-dump.json', JSON.stringify(meaningful));

            // --- WRITE METHOD 2: Append History for Humans (NDJSON) ---
            // We create a wrapper object with a timestamp
            const historyEntry = {
                timestamp: Date.now(),
                coverage: meaningful
            };
            
            // Append with a newline '\n' at the end
            // .jsonl = JSON Lines format
            fs.appendFileSync('coverage/trace-history.jsonl', JSON.stringify(historyEntry) + '\n');

            console.error('[CovHook] DUMP_COMPLETE');
        });
    });

} catch (e) {
    console.error('[CovHook] CRITICAL FAILURE:', e);
}