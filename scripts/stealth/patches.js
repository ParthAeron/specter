(function() {
    // The placeholder %SESSION_SEED% is replaced dynamically by Python with a numeric literal.
    const SEED = %SESSION_SEED%;
    
    // Seeded PRNG (Mulberry32) to ensure noise is deterministic per session
    function createRandom(seedVal) {
        let h = seedVal * 123456789;
        return function() {
            let t = h += 0x6D2B79F5;
            t = Math.imul(t ^ (t >>> 15), t | 1);
            t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
            return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
        };
    }
    const rand = createRandom(SEED);

    // Keep track of masked functions to spoof .toString()
    const toStringMap = new Map();
    const originalToString = Function.prototype.toString;

    Function.prototype.toString = function() {
        if (toStringMap.has(this)) {
            return toStringMap.get(this);
        }
        return originalToString.call(this);
    };
    toStringMap.set(Function.prototype.toString, "function toString() { [native code] }");

    function maskFunction(obj, prop, replacementFunc, nativeName) {
        const originalFunc = obj[prop];
        obj[prop] = replacementFunc;
        // Map string representation to look native
        toStringMap.set(replacementFunc, `function ${nativeName || prop}() { [native code] }`);
        
        // Retain function name and length properties
        if (originalFunc) {
            Object.defineProperty(replacementFunc, 'name', { value: originalFunc.name, writable: false });
            Object.defineProperty(replacementFunc, 'length', { value: originalFunc.length, writable: false });
        }
    }

    // 1. Remove navigator.webdriver
    try {
        if (Navigator.prototype.hasOwnProperty('webdriver')) {
            delete Navigator.prototype.webdriver;
        }
    } catch (e) {}

    // 2. Restore window.chrome
    window.chrome = {
        runtime: {},
        loadTimes: function() {},
        csi: function() {},
        app: {}
    };

    // 3. Spoof Plugins
    const pluginData = [
        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: 'Redirects PDF requests' },
        { name: 'Native Client', filename: 'internal-nacl-plugin', description: 'Native Client executable' }
    ];

    function createMockPluginArray() {
        const plugins = [];
        pluginData.forEach(p => {
            const plugin = Object.create(Plugin.prototype);
            Object.defineProperties(plugin, {
                name: { get: () => p.name },
                filename: { get: () => p.filename },
                description: { get: () => p.description },
                length: { get: () => 0 }
            });
            plugins.push(plugin);
        });

        const pluginArray = Object.create(PluginArray.prototype);
        Object.defineProperties(pluginArray, {
            length: { get: () => plugins.length },
            item: { value: (idx) => plugins[idx] },
            namedItem: { value: (name) => plugins.find(p => p.name === name) || null }
        });
        
        // Add indexing support
        plugins.forEach((p, idx) => {
            Object.defineProperty(pluginArray, idx, { get: () => p });
        });
        
        return pluginArray;
    }

    Object.defineProperty(navigator, 'plugins', { get: () => createMockPluginArray() });

    // 4. Languages, Hardware, and Memory
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

    // 5. Screen outer bounds
    Object.defineProperty(window, 'outerWidth', { get: () => window.innerWidth || 1920 });
    Object.defineProperty(window, 'outerHeight', { get: () => window.innerHeight || 1080 });

    // 6. Focus
    maskFunction(document, 'hasFocus', () => true);

    // 7. WebGL/WebGL2 String overrides
    const webglOverride = function(originalGetParameter) {
        return function(parameter) {
            // UNMASKED_VENDOR_WEBGL = 37445
            if (parameter === 37445) return 'Intel Inc.';
            // UNMASKED_RENDERER_WEBGL = 37446
            if (parameter === 37446) return 'Intel Iris OpenGL Engine';
            // VENDOR = 7936
            if (parameter === 7936) return 'WebKit';
            // RENDERER = 7937
            if (parameter === 7937) return 'WebKit WebGL';
            return originalGetParameter.call(this, parameter);
        };
    };

    if (window.WebGLRenderingContext) {
        maskFunction(
            WebGLRenderingContext.prototype,
            'getParameter',
            webglOverride(WebGLRenderingContext.prototype.getParameter),
            'getParameter'
        );
    }
    if (window.WebGL2RenderingContext) {
        maskFunction(
            WebGL2RenderingContext.prototype,
            'getParameter',
            webglOverride(WebGL2RenderingContext.prototype.getParameter),
            'getParameter'
        );
    }

    // 8. Permissions query override
    if (window.Permissions && Permissions.prototype.query) {
        const originalQuery = Permissions.prototype.query;
        maskFunction(Permissions.prototype, 'query', function(queryObj) {
            if (queryObj && (queryObj.name === 'notifications' || queryObj.name === 'geolocation')) {
                return Promise.resolve(Object.create(PermissionStatus.prototype, {
                    state: { get: () => 'prompt' },
                    onchange: { get: () => null, set: () => {} }
                }));
            }
            return originalQuery.call(this, queryObj);
        }, 'query');
    }

    // 9. WebRTC leaks blocking
    try {
        delete window.RTCPeerConnection;
        delete window.RTCSessionDescription;
        delete window.RTCIceCandidate;
        delete window.MediaStreamTrack;
    } catch (e) {}

    // 10. Connection Info
    Object.defineProperty(navigator, 'connection', {
        get: () => ({
            effectiveType: '4g',
            rtt: 50,
            downlink: 10,
            saveData: false,
            onchange: null
        })
    });

    // 11. Speech Synthesis Voices
    if (window.speechSynthesis) {
        const mockVoices = [
            { name: 'Google US English', lang: 'en-US', default: true, localService: true, voiceURI: 'Google US English' },
            { name: 'Google UK English Male', lang: 'en-GB', default: false, localService: true, voiceURI: 'Google UK English Male' }
        ];
        maskFunction(speechSynthesis, 'getVoices', () => mockVoices, 'getVoices');
    }

    // 12. Seed-Seeded Deterministic Canvas Noise
    const canvasNoise = (ctx) => {
        // Apply tiny offset to a single pixel in the context
        const imgData = ctx.getImageData(0, 0, 10, 10);
        for (let i = 0; i < imgData.data.length; i += 4) {
            // Apply slight deterministic noise based on the seed
            const noise = Math.floor(rand() * 2);
            imgData.data[i] = (imgData.data[i] + noise) % 256;
        }
        ctx.putImageData(imgData, 0, 0);
    };

    if (window.HTMLCanvasElement) {
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        maskFunction(HTMLCanvasElement.prototype, 'toDataURL', function(...args) {
            const ctx = this.getContext('2d');
            if (ctx) {
                try { canvasNoise(ctx); } catch (e) {}
            }
            return originalToDataURL.apply(this, args);
        }, 'toDataURL');

        const originalToBlob = HTMLCanvasElement.prototype.toBlob;
        maskFunction(HTMLCanvasElement.prototype, 'toBlob', function(callback, ...args) {
            const ctx = this.getContext('2d');
            if (ctx) {
                try { canvasNoise(ctx); } catch (e) {}
            }
            return originalToBlob.call(this, callback, ...args);
        }, 'toBlob');

        const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;
        maskFunction(CanvasRenderingContext2D.prototype, 'getImageData', function(x, y, w, h) {
            try { canvasNoise(self); } catch (e) {}
            return originalGetImageData.call(this, x, y, w, h);
        }, 'getImageData');
    }
})();
