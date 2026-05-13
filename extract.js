// ============================================
// MemeMiningBot - API & InitData Extractor
// ============================================
// STEP 1: Buka game MemeMiningBot di Telegram
// STEP 2: Tekan F12 → Console → paste + run
// STEP 3: Lihat output di console — semua info API akan ter-print
// ============================================

(function() {
    console.log('=== MemeMiningBot API Extractor ===\n');

    // 1. InitData dari Telegram WebApp
    try {
        if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initData) {
            const initData = window.Telegram.WebApp.initData;
            console.log('✅ INITDATA:');
            console.log(initData);
            console.log('');
        } else {
            console.log('❌ Telegram.WebApp.initData NOT FOUND');
        }
    } catch(e) {
        console.log('❌ Telegram.WebApp ERROR:', e.message);
    }

    // 2. Base URL / API domain
    const currentURL = window.location.href;
    console.log('📍 PAGE URL:', currentURL);
    console.log('🌐 ORIGIN:', window.location.origin);
    console.log('');

    // 3. Cek cookies — cari session token
    console.log('🍪 COOKIES:');
    document.cookie.split(';').forEach(c => {
        const [name, value] = c.trim().split('=');
        console.log(`   ${name} = ${value ? value.substring(0, 100) : '(empty)'}`);
    });
    console.log('');

    // 4. Cek localStorage — sering nyimpen auth token
    console.log('💾 LOCAL STORAGE:');
    for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        const val = localStorage.getItem(key);
        const short = val ? val.substring(0, 80) : '(null)';
        console.log(`   ${key} = ${short}`);
    }
    console.log('');

    // 5. Coba intercept Network — print semua fetch/XHR calls
    console.log('📡 Monitoring network requests (30 detik)...');
    console.log('   Click something in the game to trigger API calls!');
    console.log('');

    const origFetch = window.fetch;
    window.fetch = function(...args) {
        const url = typeof args[0] === 'string' ? args[0] : args[0].url;
        const method = args[1]?.method || 'GET';
        const body = args[1]?.body;
        console.log(`🔵 FETCH ${method} ${url}`);
        if (body) {
            try {
                console.log(`   Body: ${typeof body === 'string' ? body.substring(0, 200) : JSON.stringify(body)}`);
            } catch(e) {}
        }
        return origFetch.apply(this, args).then(resp => {
            console.log(`   → Response ${resp.status}`);
            return resp;
        });
    };

    // 6. Coba cari global state / config
    console.log('🔍 SEARCHING for API config in window...');
    const keywords = ['api', 'token', 'session', 'auth', 'baseUrl', 'config', 'endpoint'];
    const found = [];
    for (const key of Object.keys(window)) {
        const lower = key.toLowerCase();
        if (keywords.some(k => lower.includes(k))) {
            try {
                const val = window[key];
                if (typeof val === 'string' && val.length < 200) {
                    found.push(`window.${key} = ${val}`);
                } else if (typeof val === 'object' && val !== null) {
                    found.push(`window.${key} = [object]`);
                    // Try to stringify if small
                    try {
                        const str = JSON.stringify(val);
                        if (str.length < 200) found.push(`   → ${str}`);
                    } catch(e) {}
                }
            } catch(e) {}
        }
    }
    if (found.length > 0) {
        found.slice(0, 15).forEach(f => console.log('   ' + f));
    } else {
        console.log('   (no obvious API config found in window)');
    }

    console.log('\n=== DONE ===');
    console.log('📋 Now click/tap something in the game and watch for API calls!');
})();