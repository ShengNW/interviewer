(function (global, factory) {
    typeof exports === 'object' && typeof module !== 'undefined' ? factory(exports) :
    typeof define === 'function' && define.amd ? define(['exports'], factory) :
    (global = typeof globalThis !== 'undefined' ? globalThis : global || self, factory(global.YeYingWeb3 = {}));
})(this, (function (exports) { 'use strict';

    const YEYING_RDNS = 'io.github.yeying';
    const DEFAULT_TIMEOUT = 1000;
    function getWindowEthereum() {
        if (typeof window === 'undefined')
            return null;
        return window.ethereum || null;
    }
    function isYeYingProvider(provider, info) {
        if (!provider)
            return false;
        if (provider.isYeYing)
            return true;
        const name = (info?.name || '').toLowerCase();
        const rdns = (info?.rdns || '').toLowerCase();
        return rdns === YEYING_RDNS || name.includes('yeying');
    }
    function selectBestProvider(candidates, preferYeYing) {
        if (candidates.length === 0)
            return null;
        if (preferYeYing) {
            const yeying = candidates.find(c => isYeYingProvider(c.provider, c.info));
            if (yeying)
                return yeying.provider;
        }
        return candidates[0].provider;
    }
    async function getProvider(options = {}) {
        const preferYeYing = options.preferYeYing !== false;
        const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT;
        const windowProvider = getWindowEthereum();
        if (preferYeYing && isYeYingProvider(windowProvider)) {
            return windowProvider;
        }
        if (typeof window === 'undefined') {
            return windowProvider;
        }
        const discovered = [];
        let resolved = false;
        return await new Promise(resolve => {
            const cleanup = () => {
                window.removeEventListener('eip6963:announceProvider', onAnnounce);
                window.removeEventListener('ethereum#initialized', onEthereumInitialized);
                if (timeoutId)
                    clearTimeout(timeoutId);
            };
            const safeResolve = (provider) => {
                if (resolved)
                    return;
                resolved = true;
                cleanup();
                resolve(provider);
            };
            const onAnnounce = (event) => {
                const detail = event.detail;
                if (!detail?.provider)
                    return;
                discovered.push(detail);
                if (preferYeYing && isYeYingProvider(detail.provider, detail.info)) {
                    safeResolve(detail.provider);
                }
            };
            const onEthereumInitialized = () => {
                const injected = getWindowEthereum();
                if (preferYeYing && isYeYingProvider(injected)) {
                    safeResolve(injected);
                }
            };
            window.addEventListener('eip6963:announceProvider', onAnnounce);
            window.addEventListener('ethereum#initialized', onEthereumInitialized, { once: true });
            const timeoutId = setTimeout(() => {
                if (resolved)
                    return;
                const best = selectBestProvider(discovered, preferYeYing) ||
                    windowProvider ||
                    getWindowEthereum();
                safeResolve(best || null);
            }, timeoutMs);
            try {
                window.dispatchEvent(new Event('eip6963:requestProvider'));
            }
            catch {
                // Ignore if browser doesn't support CustomEvent target
            }
            if (!preferYeYing && windowProvider) {
                safeResolve(windowProvider);
            }
        });
    }
    async function requireProvider(options = {}) {
        const provider = await getProvider(options);
        if (!provider) {
            throw new Error('No injected wallet provider found');
        }
        return provider;
    }
    async function requestAccounts(options = {}) {
        const provider = options.provider || (await requireProvider());
        const accounts = (await provider.request({
            method: 'eth_requestAccounts',
        }));
        return Array.isArray(accounts) ? accounts : [];
    }
    async function getAccounts(provider) {
        const p = provider || (await requireProvider());
        const accounts = (await p.request({ method: 'eth_accounts' }));
        return Array.isArray(accounts) ? accounts : [];
    }
    async function getChainId(provider) {
        const p = provider || (await requireProvider());
        const chainId = (await p.request({ method: 'eth_chainId' }));
        return typeof chainId === 'string' ? chainId : null;
    }
    async function getBalance(provider, address, blockTag = 'latest') {
        const p = provider || (await requireProvider());
        let target = address;
        if (!target) {
            const accounts = await getAccounts(p);
            target = accounts[0];
        }
        if (!target) {
            throw new Error('No account available for balance');
        }
        const balance = (await p.request({
            method: 'eth_getBalance',
            params: [target, blockTag],
        }));
        if (typeof balance !== 'string') {
            throw new Error('Invalid balance response');
        }
        return balance;
    }
    function onAccountsChanged(provider, handler) {
        provider.on?.('accountsChanged', handler);
        return () => provider.removeListener?.('accountsChanged', handler);
    }
    function onChainChanged(provider, handler) {
        provider.on?.('chainChanged', handler);
        return () => provider.removeListener?.('chainChanged', handler);
    }

    function normalizeBaseUrl$1(baseUrl) {
        return baseUrl.replace(/\/+$/, '');
    }
    function joinUrl$1(baseUrl, path) {
        const trimmed = path.replace(/^\/+/, '');
        return `${normalizeBaseUrl$1(baseUrl)}/${trimmed}`;
    }
    const DEFAULT_TOKEN_KEY = 'authToken';
    let cachedAccessToken = null;
    let refreshInFlight = null;
    function resolveTokenKey(options) {
        return options?.tokenStorageKey || DEFAULT_TOKEN_KEY;
    }
    function shouldStoreToken(options) {
        return options?.storeToken !== false;
    }
    function resolveFetcher(options) {
        return options?.fetcher || fetch;
    }
    function resolveCredentials(options) {
        return options?.credentials ?? 'include';
    }
    function readStoredToken(options) {
        if (!shouldStoreToken(options))
            return null;
        if (typeof localStorage === 'undefined')
            return null;
        const key = resolveTokenKey(options);
        return localStorage.getItem(key);
    }
    function persistToken(token, options) {
        cachedAccessToken = token;
        if (!shouldStoreToken(options))
            return;
        if (typeof localStorage === 'undefined')
            return;
        const key = resolveTokenKey(options);
        if (!token) {
            localStorage.removeItem(key);
        }
        else {
            localStorage.setItem(key, token);
        }
    }
    function getAccessToken(options) {
        if (cachedAccessToken)
            return cachedAccessToken;
        const stored = readStoredToken(options);
        if (stored) {
            cachedAccessToken = stored;
        }
        return stored;
    }
    function setAccessToken(token, options) {
        persistToken(token, options);
    }
    function clearAccessToken(options) {
        cachedAccessToken = null;
        if (typeof localStorage === 'undefined')
            return;
        const key = resolveTokenKey(options);
        localStorage.removeItem(key);
    }
    async function resolveAddress$1(provider, address) {
        if (address)
            return address;
        let accounts = await getAccounts(provider);
        if (!accounts[0]) {
            const requested = (await provider.request({
                method: 'eth_requestAccounts',
            }));
            if (Array.isArray(requested)) {
                accounts = requested;
            }
        }
        if (!accounts[0]) {
            throw new Error('No account available');
        }
        return accounts[0];
    }
    function extractChallenge(payload) {
        if (!payload || typeof payload !== 'object')
            return null;
        const data = payload;
        const envelope = data.data;
        if (envelope) {
            const value = envelope.challenge;
            if (typeof value === 'string')
                return value;
        }
        const direct = data.challenge || data.result;
        if (typeof direct === 'string')
            return direct;
        if (direct && typeof direct === 'object') {
            const nested = direct.challenge;
            if (typeof nested === 'string')
                return nested;
        }
        const body = data.body;
        if (body) {
            const bodyResult = body.result;
            if (typeof bodyResult === 'string')
                return bodyResult;
            if (bodyResult && typeof bodyResult === 'object') {
                const nested = bodyResult.challenge;
                if (typeof nested === 'string')
                    return nested;
            }
        }
        return null;
    }
    function extractToken(payload) {
        if (!payload || typeof payload !== 'object')
            return null;
        const data = payload;
        const envelope = data.data;
        if (envelope) {
            const value = envelope.token;
            if (typeof value === 'string')
                return value;
        }
        const direct = data.token || data.result;
        if (typeof direct === 'string')
            return direct;
        const body = data.body;
        if (body) {
            const bodyToken = body.token;
            if (typeof bodyToken === 'string')
                return bodyToken;
            const bodyResult = body.result;
            if (typeof bodyResult === 'string')
                return bodyResult;
            if (bodyResult && typeof bodyResult === 'object') {
                const nested = bodyResult.token;
                if (typeof nested === 'string')
                    return nested;
            }
        }
        return null;
    }
    async function signMessage(options) {
        const provider = options.provider || (await requireProvider());
        const address = await resolveAddress$1(provider, options.address);
        const method = options.method || 'personal_sign';
        const params = method === 'eth_sign'
            ? [address, options.message]
            : [options.message, address];
        const signature = await provider.request({
            method,
            params,
        });
        if (typeof signature !== 'string') {
            throw new Error('Invalid signature response');
        }
        return signature;
    }
    async function loginWithChallenge(options = {}) {
        const provider = options.provider || (await requireProvider());
        const address = await resolveAddress$1(provider, options.address);
        const fetcher = resolveFetcher(options);
        const credentials = resolveCredentials(options);
        const baseUrl = options.baseUrl || '/api/v1/public/auth';
        const challengeUrl = joinUrl$1(baseUrl, options.challengePath || 'challenge');
        const verifyUrl = joinUrl$1(baseUrl, options.verifyPath || 'verify');
        const challengeBody = {
            address,
        };
        const challengeRes = await fetcher(challengeUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                accept: 'application/json',
            },
            credentials,
            body: JSON.stringify(challengeBody),
        });
        if (!challengeRes.ok) {
            const text = await challengeRes.text();
            throw new Error(`Challenge request failed: ${challengeRes.status} ${text}`);
        }
        const challengePayload = await challengeRes.json();
        const challenge = extractChallenge(challengePayload);
        if (!challenge) {
            throw new Error('Challenge response missing challenge');
        }
        const signature = await signMessage({
            provider,
            address,
            message: challenge,
            method: options.signMethod || 'personal_sign',
        });
        const verifyBody = {
            address,
            signature,
        };
        const verifyRes = await fetcher(verifyUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                accept: 'application/json',
            },
            credentials,
            body: JSON.stringify(verifyBody),
        });
        if (!verifyRes.ok) {
            const text = await verifyRes.text();
            throw new Error(`Verify request failed: ${verifyRes.status} ${text}`);
        }
        const verifyPayload = await verifyRes.json();
        const token = extractToken(verifyPayload);
        if (!token) {
            throw new Error('Verify response missing token');
        }
        persistToken(token, options);
        return {
            token,
            address,
            signature,
            challenge,
            response: verifyPayload,
        };
    }
    async function refreshAccessToken(options = {}) {
        if (refreshInFlight) {
            return refreshInFlight;
        }
        const task = (async () => {
            const fetcher = resolveFetcher(options);
            const credentials = resolveCredentials(options);
            const baseUrl = options.baseUrl || '/api/v1/public/auth';
            const refreshUrl = joinUrl$1(baseUrl, options.refreshPath || 'refresh');
            const refreshRes = await fetcher(refreshUrl, {
                method: 'POST',
                headers: {
                    accept: 'application/json',
                },
                credentials,
            });
            if (!refreshRes.ok) {
                const text = await refreshRes.text();
                throw new Error(`Refresh request failed: ${refreshRes.status} ${text}`);
            }
            const refreshPayload = await refreshRes.json();
            const token = extractToken(refreshPayload);
            if (!token) {
                throw new Error('Refresh response missing token');
            }
            persistToken(token, options);
            return { token, response: refreshPayload };
        })();
        refreshInFlight = task;
        try {
            return await task;
        }
        finally {
            refreshInFlight = null;
        }
    }
    async function logout(options = {}) {
        const fetcher = resolveFetcher(options);
        const credentials = resolveCredentials(options);
        const baseUrl = options.baseUrl || '/api/v1/public/auth';
        const logoutUrl = joinUrl$1(baseUrl, options.logoutPath || 'logout');
        const logoutRes = await fetcher(logoutUrl, {
            method: 'POST',
            headers: {
                accept: 'application/json',
            },
            credentials,
        });
        if (!logoutRes.ok) {
            const text = await logoutRes.text();
            throw new Error(`Logout request failed: ${logoutRes.status} ${text}`);
        }
        let payload = null;
        try {
            payload = await logoutRes.json();
        }
        catch {
            payload = null;
        }
        clearAccessToken(options);
        return { response: payload };
    }
    async function authFetch(input, init = {}, options = {}) {
        const fetcher = resolveFetcher(options);
        const credentials = resolveCredentials(options);
        const retryOnUnauthorized = options.retryOnUnauthorized !== false;
        const performRequest = async (tokenOverride) => {
            const headers = new Headers(init.headers || {});
            const token = tokenOverride ?? options.accessToken ?? getAccessToken(options);
            if (token && !headers.has('Authorization')) {
                headers.set('Authorization', `Bearer ${token}`);
            }
            return fetcher(input, {
                ...init,
                headers,
                credentials,
            });
        };
        const initialRes = await performRequest();
        if (initialRes.status !== 401 || !retryOnUnauthorized) {
            return initialRes;
        }
        try {
            const refreshed = await refreshAccessToken(options);
            return await performRequest(refreshed.token);
        }
        catch {
            return initialRes;
        }
    }

    const DEFAULT_SESSION_ID = 'default';
    const DEFAULT_SESSION_TTL = 24 * 60 * 60 * 1000;
    const DEFAULT_UCAN_TTL = 5 * 60 * 1000;
    const DB_NAME = 'yeying-web3';
    const DB_STORE = 'ucan-sessions';
    const textEncoder = new TextEncoder();
    function toBase64Url(data) {
        const bytes = data instanceof Uint8Array ? data : new Uint8Array(data);
        let binary = '';
        for (let i = 0; i < bytes.length; i += 1) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    }
    function encodeJson(value) {
        return toBase64Url(textEncoder.encode(JSON.stringify(value)));
    }
    function randomNonce(bytes = 16) {
        const buffer = new Uint8Array(bytes);
        crypto.getRandomValues(buffer);
        return Array.from(buffer)
            .map(b => b.toString(16).padStart(2, '0'))
            .join('');
    }
    function normalizeExpiry(exp, fallbackMs) {
        return Date.now() + fallbackMs;
    }
    function openDb() {
        if (typeof indexedDB === 'undefined') {
            return Promise.reject(new Error('IndexedDB not available'));
        }
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, 1);
            request.onupgradeneeded = () => {
                const db = request.result;
                if (!db.objectStoreNames.contains(DB_STORE)) {
                    db.createObjectStore(DB_STORE, { keyPath: 'id' });
                }
            };
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }
    async function readSessionRecord(id) {
        try {
            const db = await openDb();
            return await new Promise((resolve, reject) => {
                const tx = db.transaction(DB_STORE, 'readonly');
                const store = tx.objectStore(DB_STORE);
                const request = store.get(id);
                request.onsuccess = () => resolve(request.result || null);
                request.onerror = () => reject(request.error);
            });
        }
        catch {
            return null;
        }
    }
    async function writeSessionRecord(record) {
        try {
            const db = await openDb();
            await new Promise((resolve, reject) => {
                const tx = db.transaction(DB_STORE, 'readwrite');
                const store = tx.objectStore(DB_STORE);
                const request = store.put(record);
                request.onsuccess = () => resolve();
                request.onerror = () => reject(request.error);
            });
        }
        catch {
            // ignore storage failures
        }
    }
    async function deleteSessionRecord(id) {
        try {
            const db = await openDb();
            await new Promise((resolve, reject) => {
                const tx = db.transaction(DB_STORE, 'readwrite');
                const store = tx.objectStore(DB_STORE);
                const request = store.delete(id);
                request.onsuccess = () => resolve();
                request.onerror = () => reject(request.error);
            });
        }
        catch {
            // ignore storage failures
        }
    }
    async function getUcanSession(id = DEFAULT_SESSION_ID, provider) {
        const walletProvider = provider || (typeof window !== 'undefined'
            ? await getProvider({ preferYeYing: true })
            : null);
        if (!walletProvider)
            return null;
        try {
            return await requestWalletUcanSession(walletProvider, { id });
        }
        catch {
            return null;
        }
    }
    async function requestWalletUcanSession(provider, options) {
        const sessionId = options.id || DEFAULT_SESSION_ID;
        const result = (await provider.request({
            method: 'yeying_ucan_session',
            params: [
                {
                    sessionId,
                    expiresInMs: options.expiresInMs,
                    forceNew: options.forceNew,
                },
            ],
        }));
        if (!result || typeof result.did !== 'string') {
            throw new Error('Invalid wallet UCAN session response');
        }
        const createdAt = typeof result.createdAt === 'number' ? result.createdAt : Date.now();
        const expiresAt = typeof result.expiresAt === 'number' ? result.expiresAt : null;
        const existing = await readSessionRecord(sessionId);
        const nextRecord = {
            id: result.id || sessionId,
            did: result.did,
            createdAt,
            expiresAt,
            root: existing?.root,
        };
        if (nextRecord.root && nextRecord.root.aud && nextRecord.root.aud !== nextRecord.did) {
            nextRecord.root = undefined;
        }
        await writeSessionRecord(nextRecord);
        return {
            id: result.id || sessionId,
            did: result.did,
            createdAt,
            expiresAt,
            signer: async (signingInput, payload) => {
                const signatureResult = (await provider.request({
                    method: 'yeying_ucan_sign',
                    params: [
                        {
                            sessionId,
                            signingInput,
                            payload,
                        },
                    ],
                }));
                if (typeof signatureResult === 'string') {
                    return signatureResult;
                }
                if (signatureResult && typeof signatureResult.signature === 'string') {
                    return signatureResult.signature;
                }
                throw new Error('Invalid wallet UCAN signature response');
            },
        };
    }
    async function createUcanSession(options = {}) {
        const provider = options.provider || (typeof window !== 'undefined'
            ? await getProvider({ preferYeYing: true })
            : null);
        if (!provider) {
            throw new Error('No wallet provider for UCAN session');
        }
        return await requestWalletUcanSession(provider, options);
    }
    async function clearUcanSession(id = DEFAULT_SESSION_ID) {
        await deleteSessionRecord(id);
    }
    async function storeUcanRoot(root, id = DEFAULT_SESSION_ID) {
        const record = await readSessionRecord(id);
        const createdAt = record?.createdAt ?? Date.now();
        const expiresAt = record?.expiresAt ?? null;
        const did = record?.did || root.aud;
        const nextRecord = {
            id,
            did,
            createdAt,
            expiresAt,
            root,
        };
        await writeSessionRecord(nextRecord);
    }
    async function getStoredUcanRoot(id = DEFAULT_SESSION_ID) {
        const record = await readSessionRecord(id);
        return record?.root || null;
    }
    function capsEqual(a, b) {
        return JSON.stringify(a || []) === JSON.stringify(b || []);
    }
    function isRootExpired(root, nowMs) {
        return Boolean(root.exp && nowMs > root.exp);
    }
    async function getOrCreateUcanRoot(options) {
        const provider = options.provider || (await requireProvider());
        const session = options.session || (await createUcanSession({ id: options.sessionId, provider }));
        const nowMs = Date.now();
        const stored = await getStoredUcanRoot(session.id);
        if (stored &&
            (!stored.aud || stored.aud === session.did) &&
            capsEqual(stored.cap, options.capabilities) &&
            !isRootExpired(stored, nowMs)) {
            return stored;
        }
        return await createRootUcan({ ...options, provider, session });
    }
    function buildUcanStatement(payload) {
        return `UCAN-AUTH ${JSON.stringify(payload)}`;
    }
    function buildSiweMessage(params) {
        const lines = [
            `${params.domain} wants you to sign in with your Ethereum account:`,
            params.address,
            '',
            params.statement,
            '',
            `URI: ${params.uri}`,
            'Version: 1',
            `Chain ID: ${params.chainId}`,
            `Nonce: ${params.nonce}`,
            `Issued At: ${params.issuedAt}`,
        ];
        if (params.expirationTime) {
            lines.push(`Expiration Time: ${params.expirationTime}`);
        }
        return lines.join('\n');
    }
    async function resolveAddress(provider, address) {
        if (address)
            return address;
        let accounts = await getAccounts(provider);
        if (!accounts[0]) {
            const requested = (await provider.request({
                method: 'eth_requestAccounts',
            }));
            if (Array.isArray(requested)) {
                accounts = requested;
            }
        }
        if (!accounts[0])
            throw new Error('No account available');
        return accounts[0];
    }
    async function signWithProvider(provider, address, message) {
        const signature = await provider.request({
            method: 'personal_sign',
            params: [message, address],
        });
        if (typeof signature !== 'string') {
            throw new Error('Invalid signature response');
        }
        return signature;
    }
    async function createRootUcan(options) {
        const provider = options.provider || (await requireProvider());
        const session = options.session || (await createUcanSession({ id: options.sessionId, provider }));
        const address = await resolveAddress(provider, options.address);
        const chainId = options.chainId || (await getChainId(provider)) || '1';
        const domain = options.domain || (typeof window !== 'undefined' ? window.location.host : 'localhost');
        const uri = options.uri || (typeof window !== 'undefined' ? window.location.origin : 'http://localhost');
        const nonce = options.nonce || randomNonce(8);
        const exp = normalizeExpiry(undefined, options.expiresInMs ?? DEFAULT_SESSION_TTL);
        const nbf = options.notBeforeMs;
        const statementPayload = {
            aud: session.did,
            cap: options.capabilities,
            exp,
        };
        if (nbf)
            statementPayload.nbf = nbf;
        const statement = options.statement || buildUcanStatement(statementPayload);
        const issuedAt = new Date().toISOString();
        const expirationTime = new Date(exp).toISOString();
        const message = buildSiweMessage({
            domain,
            address,
            statement,
            uri,
            chainId,
            nonce,
            issuedAt,
            expirationTime,
        });
        const signature = await signWithProvider(provider, address, message);
        const root = {
            type: 'siwe',
            iss: `did:pkh:eth:${address.toLowerCase()}`,
            aud: session.did,
            cap: options.capabilities,
            exp,
            nbf,
            siwe: {
                message,
                signature,
            },
        };
        await storeUcanRoot(root, session.id);
        return root;
    }
    async function signUcanPayload(payload, session) {
        const header = { alg: 'EdDSA', typ: 'UCAN' };
        const headerB64 = encodeJson(header);
        const payloadB64 = encodeJson(payload);
        const signingInput = `${headerB64}.${payloadB64}`;
        let signatureB64;
        if (session.signer) {
            signatureB64 = await session.signer(signingInput, payload);
        }
        else {
            if (!session.privateKey) {
                throw new Error('Missing UCAN session key');
            }
            const data = textEncoder.encode(signingInput);
            const signature = await crypto.subtle.sign('Ed25519', session.privateKey, data);
            signatureB64 = toBase64Url(signature);
        }
        return `${headerB64}.${payloadB64}.${signatureB64}`;
    }
    async function resolveProofs(options, issuer) {
        if (options.proofs && options.proofs.length > 0)
            return options.proofs;
        const stored = await getStoredUcanRoot(options.sessionId || DEFAULT_SESSION_ID);
        if (!stored) {
            throw new Error('Missing UCAN proof chain');
        }
        if (issuer?.did && stored.aud && stored.aud !== issuer.did) {
            throw new Error('UCAN root audience mismatch');
        }
        return [stored];
    }
    async function createDelegationUcan(options) {
        const issuer = options.issuer || (await createUcanSession({
            id: options.sessionId,
            provider: options.provider,
        }));
        if (!issuer)
            throw new Error('Missing UCAN session key');
        const exp = normalizeExpiry(undefined, options.expiresInMs ?? DEFAULT_UCAN_TTL);
        const payload = {
            iss: issuer.did,
            aud: options.audience,
            cap: options.capabilities,
            exp,
            nbf: options.notBeforeMs,
            prf: await resolveProofs(options, issuer),
        };
        return await signUcanPayload(payload, issuer);
    }
    async function createInvocationUcan(options) {
        const issuer = options.issuer || (await createUcanSession({
            id: options.sessionId,
            provider: options.provider,
        }));
        if (!issuer)
            throw new Error('Missing UCAN session key');
        const exp = normalizeExpiry(undefined, options.expiresInMs ?? DEFAULT_UCAN_TTL);
        const payload = {
            iss: issuer.did,
            aud: options.audience,
            cap: options.capabilities,
            exp,
            nbf: options.notBeforeMs,
            prf: await resolveProofs(options, issuer),
        };
        return await signUcanPayload(payload, issuer);
    }
    async function authUcanFetch(input, init = {}, options = {}) {
        const fetcher = options.fetcher || fetch;
        let token = options.ucan;
        if (!token) {
            if (!options.audience || !options.capabilities) {
                throw new Error('Missing UCAN audience or capabilities');
            }
            token = await createInvocationUcan({
                issuer: options.issuer,
                sessionId: options.sessionId,
                provider: options.provider,
                audience: options.audience,
                capabilities: options.capabilities,
                expiresInMs: options.expiresInMs,
                notBeforeMs: options.notBeforeMs,
                proofs: options.proofs,
            });
        }
        const headers = new Headers(init.headers || {});
        headers.set('Authorization', `Bearer ${token}`);
        return fetcher(input, {
            ...init,
            headers,
        });
    }

    function normalizeBaseUrl(baseUrl) {
        return baseUrl.replace(/\/+$/, '');
    }
    function normalizePrefix(prefix) {
        if (!prefix || prefix === '/')
            return '';
        let next = prefix.startsWith('/') ? prefix : `/${prefix}`;
        next = next.replace(/\/+$/, '');
        return next;
    }
    function normalizePath(path) {
        if (!path || path === '/')
            return '/';
        const next = path.startsWith('/') ? path : `/${path}`;
        return encodeURI(next);
    }
    function joinUrl(baseUrl, path) {
        const base = normalizeBaseUrl(baseUrl);
        const suffix = path.startsWith('/') ? path : `/${path}`;
        return `${base}${suffix}`;
    }
    function resolveAuthHeader(auth, token) {
        if (auth?.type === 'bearer') {
            return `Bearer ${auth.token}`;
        }
        if (auth?.type === 'basic') {
            const raw = `${auth.username}:${auth.password}`;
            return `Basic ${btoa(raw)}`;
        }
        if (token) {
            return `Bearer ${token}`;
        }
        return null;
    }
    class WebDavClient {
        baseUrl;
        prefix;
        auth;
        token;
        fetcher;
        credentials;
        constructor(options) {
            this.baseUrl = normalizeBaseUrl(options.baseUrl);
            this.prefix = normalizePrefix(options.prefix);
            this.auth = options.auth;
            this.token = options.token;
            this.fetcher = options.fetcher || ((input, init) => fetch(input, init));
            this.credentials = options.credentials;
        }
        setToken(token) {
            this.token = token || undefined;
        }
        setAuth(auth) {
            this.auth = auth;
        }
        buildUrl(path) {
            const webdavPath = `${this.prefix}${normalizePath(path)}`;
            return `${this.baseUrl}${webdavPath}`;
        }
        buildHeaders(options) {
            const headers = new Headers(options?.headers || {});
            const authHeader = resolveAuthHeader(options?.auth || this.auth, options?.token || this.token);
            if (authHeader) {
                headers.set('Authorization', authHeader);
            }
            if (options?.depth !== undefined) {
                headers.set('Depth', String(options.depth));
            }
            if (typeof options?.overwrite === 'boolean') {
                headers.set('Overwrite', options.overwrite ? 'T' : 'F');
            }
            if (options?.contentType) {
                headers.set('Content-Type', options.contentType);
            }
            return headers;
        }
        async request(method, path, body, options = {}) {
            const response = await this.fetcher(this.buildUrl(path), {
                method,
                headers: this.buildHeaders(options),
                body: body ?? undefined,
                credentials: this.credentials,
                signal: options.signal,
            });
            if (!response.ok) {
                throw new Error(`WebDAV ${method} ${path} failed: ${response.status} ${response.statusText}`);
            }
            return response;
        }
        async listDirectory(path = '/', depth = 1) {
            const res = await this.request('PROPFIND', path, null, { depth });
            return await res.text();
        }
        async download(path) {
            return await this.request('GET', path);
        }
        async downloadText(path) {
            const res = await this.download(path);
            return await res.text();
        }
        async downloadArrayBuffer(path) {
            const res = await this.download(path);
            return await res.arrayBuffer();
        }
        async upload(path, content, contentType) {
            return await this.request('PUT', path, content, { contentType });
        }
        async createDirectory(path) {
            return await this.request('MKCOL', path);
        }
        async ensureDirectory(path) {
            if (!path || path === '/')
                return;
            const segments = path.split('/').filter(Boolean);
            if (segments.length === 0)
                return;
            let current = '';
            for (const segment of segments) {
                current = `${current}/${segment}`;
                const res = await this.fetcher(this.buildUrl(current), {
                    method: 'MKCOL',
                    headers: this.buildHeaders(),
                    credentials: this.credentials,
                });
                if (res.ok)
                    continue;
                if (res.status === 405)
                    continue;
                throw new Error(`WebDAV MKCOL ${current} failed: ${res.status} ${res.statusText}`);
            }
        }
        async remove(path) {
            return await this.request('DELETE', path);
        }
        async move(path, destination, overwrite = true) {
            const destinationUrl = destination.startsWith('http')
                ? destination
                : this.buildUrl(destination);
            return await this.request('MOVE', path, null, {
                headers: { Destination: destinationUrl },
                overwrite,
            });
        }
        async copy(path, destination, overwrite = true) {
            const destinationUrl = destination.startsWith('http')
                ? destination
                : this.buildUrl(destination);
            return await this.request('COPY', path, null, {
                headers: { Destination: destinationUrl },
                overwrite,
            });
        }
        async getQuota() {
            const res = await this.fetcher(joinUrl(this.baseUrl, '/api/v1/public/webdav/quota'), {
                method: 'GET',
                headers: this.buildHeaders(),
                credentials: this.credentials,
            });
            if (!res.ok) {
                throw new Error(`WebDAV quota failed: ${res.status} ${res.statusText}`);
            }
            return await res.json();
        }
        async listRecycle() {
            const res = await this.fetcher(joinUrl(this.baseUrl, '/api/v1/public/webdav/recycle/list'), {
                method: 'GET',
                headers: this.buildHeaders(),
                credentials: this.credentials,
            });
            if (!res.ok) {
                throw new Error(`WebDAV recycle list failed: ${res.status} ${res.statusText}`);
            }
            return await res.json();
        }
        async recoverRecycle(hash) {
            const res = await this.fetcher(joinUrl(this.baseUrl, '/api/v1/public/webdav/recycle/recover'), {
                method: 'POST',
                headers: this.buildHeaders({ contentType: 'application/json' }),
                body: JSON.stringify({ hash }),
                credentials: this.credentials,
            });
            if (!res.ok) {
                throw new Error(`WebDAV recycle recover failed: ${res.status} ${res.statusText}`);
            }
            return await res.json();
        }
        async deleteRecycle(hash) {
            const res = await this.fetcher(joinUrl(this.baseUrl, '/api/v1/public/webdav/recycle/permanent'), {
                method: 'DELETE',
                headers: this.buildHeaders({ contentType: 'application/json' }),
                body: JSON.stringify({ hash }),
                credentials: this.credentials,
            });
            if (!res.ok) {
                throw new Error(`WebDAV recycle delete failed: ${res.status} ${res.statusText}`);
            }
            return await res.json();
        }
        async clearRecycle() {
            const res = await this.fetcher(joinUrl(this.baseUrl, '/api/v1/public/webdav/recycle/clear'), {
                method: 'DELETE',
                headers: this.buildHeaders(),
                credentials: this.credentials,
            });
            if (!res.ok) {
                throw new Error(`WebDAV recycle clear failed: ${res.status} ${res.statusText}`);
            }
            return await res.json();
        }
    }
    function createWebDavClient(options) {
        return new WebDavClient(options);
    }

    const tokenCache = new Map();
    const TOKEN_SKEW_MS = 5000;
    function normalizeAppDir(path) {
        const trimmed = path.trim();
        if (!trimmed)
            return '/';
        let next = trimmed.startsWith('/') ? trimmed : `/${trimmed}`;
        next = next.replace(/\/+$/, '');
        return next || '/';
    }
    function sanitizeAppId(appId) {
        return appId.trim().replace(/[^a-zA-Z0-9._-]/g, '-');
    }
    function resolveAppDir(options) {
        if (options.appDir) {
            return normalizeAppDir(options.appDir);
        }
        if (options.appId) {
            return normalizeAppDir(`/apps/${sanitizeAppId(options.appId)}`);
        }
        return undefined;
    }
    function buildCapsKey(caps) {
        return JSON.stringify(caps || []);
    }
    function buildTokenCacheKey(issuer, audience, caps) {
        return `${issuer.did}|${audience}|${buildCapsKey(caps)}`;
    }
    function isTokenValid(entry, nowMs) {
        if (!entry.exp)
            return false;
        if (entry.nbf && nowMs < entry.nbf)
            return false;
        return entry.exp - TOKEN_SKEW_MS > nowMs;
    }
    function decodeBase64Url(input) {
        if (!input)
            return null;
        const base64 = input.replace(/-/g, '+').replace(/_/g, '/');
        const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=');
        try {
            if (typeof atob === 'function') {
                return atob(padded);
            }
        }
        catch {
            // ignore
        }
        try {
            const nodeBuffer = globalThis.Buffer;
            if (nodeBuffer) {
                return nodeBuffer.from(padded, 'base64').toString('utf8');
            }
        }
        catch {
            return null;
        }
        return null;
    }
    function decodeUcanPayload(token) {
        const parts = token.split('.');
        if (parts.length < 2)
            return null;
        const decoded = decodeBase64Url(parts[1]);
        if (!decoded)
            return null;
        try {
            return JSON.parse(decoded);
        }
        catch {
            return null;
        }
    }
    async function getCachedInvocationToken(options) {
        const cacheKey = buildTokenCacheKey(options.issuer, options.audience, options.capabilities);
        const cached = tokenCache.get(cacheKey);
        const nowMs = Date.now();
        if (cached && isTokenValid(cached, nowMs)) {
            return cached.token;
        }
        const token = await createInvocationUcan({
            issuer: options.issuer,
            audience: options.audience,
            capabilities: options.capabilities,
            proofs: options.proofs,
            expiresInMs: options.expiresInMs,
            notBeforeMs: options.notBeforeMs,
        });
        const payload = decodeUcanPayload(token);
        if (payload && typeof payload.exp === 'number') {
            tokenCache.set(cacheKey, {
                token,
                exp: payload.exp,
                nbf: payload.nbf,
            });
        }
        return token;
    }
    async function initWebDavStorage(options) {
        const caps = options.capabilities || options.root?.cap;
        if (!caps || caps.length === 0) {
            throw new Error('Missing UCAN capabilities for WebDAV');
        }
        const needsProvider = !options.session || !options.root;
        const provider = options.provider || (needsProvider ? await requireProvider() : undefined);
        const session = options.session ||
            (await createUcanSession({
                id: options.sessionId,
                provider,
            }));
        const nowMs = Date.now();
        let root = options.root;
        if (root && root.aud && root.aud !== session.did) {
            root = undefined;
        }
        if (root && buildCapsKey(root.cap) !== buildCapsKey(caps)) {
            root = undefined;
        }
        if (root && root.exp && nowMs > root.exp) {
            root = undefined;
        }
        if (!root) {
            root = await getOrCreateUcanRoot({
                provider: provider || (await requireProvider()),
                session,
                capabilities: caps,
                expiresInMs: options.rootExpiresInMs,
            });
        }
        const invocationCaps = options.invocationCapabilities || caps;
        const token = await getCachedInvocationToken({
            issuer: session,
            audience: options.audience,
            capabilities: invocationCaps,
            proofs: [root],
            expiresInMs: options.invocationExpiresInMs,
            notBeforeMs: options.notBeforeMs,
        });
        const client = createWebDavClient({
            baseUrl: options.baseUrl,
            prefix: options.prefix,
            token,
            fetcher: options.fetcher,
            credentials: options.credentials,
        });
        const appDir = resolveAppDir(options);
        if (appDir && options.ensureAppDir !== false) {
            await client.ensureDirectory(appDir);
        }
        return {
            client,
            token,
            appDir,
            session,
            root,
        };
    }
    async function initDappSession(options) {
        if (!options.appAuth && !options.webdav) {
            throw new Error('No init options provided');
        }
        const provider = options.provider ||
            options.appAuth?.provider ||
            options.webdav?.provider ||
            (await requireProvider());
        const result = {
            provider,
            address: options.address,
        };
        if (options.appAuth) {
            const appLogin = await loginWithChallenge({
                ...options.appAuth,
                provider: options.appAuth.provider || provider,
                address: options.appAuth.address || options.address,
            });
            result.appLogin = appLogin;
            result.address = appLogin.address;
        }
        if (options.webdav) {
            const webdav = await initWebDavStorage({
                ...options.webdav,
                provider: options.webdav.provider || provider,
            });
            result.ucanSession = webdav.session;
            result.ucanRoot = webdav.root;
            result.webdavClient = webdav.client;
            result.webdavToken = webdav.token;
            result.webdavAppDir = webdav.appDir;
        }
        return result;
    }

    exports.WebDavClient = WebDavClient;
    exports.authFetch = authFetch;
    exports.authUcanFetch = authUcanFetch;
    exports.clearAccessToken = clearAccessToken;
    exports.clearUcanSession = clearUcanSession;
    exports.createDelegationUcan = createDelegationUcan;
    exports.createInvocationUcan = createInvocationUcan;
    exports.createRootUcan = createRootUcan;
    exports.createUcanSession = createUcanSession;
    exports.createWebDavClient = createWebDavClient;
    exports.getAccessToken = getAccessToken;
    exports.getAccounts = getAccounts;
    exports.getBalance = getBalance;
    exports.getChainId = getChainId;
    exports.getOrCreateUcanRoot = getOrCreateUcanRoot;
    exports.getProvider = getProvider;
    exports.getStoredUcanRoot = getStoredUcanRoot;
    exports.getUcanSession = getUcanSession;
    exports.initDappSession = initDappSession;
    exports.initWebDavStorage = initWebDavStorage;
    exports.isYeYingProvider = isYeYingProvider;
    exports.loginWithChallenge = loginWithChallenge;
    exports.logout = logout;
    exports.onAccountsChanged = onAccountsChanged;
    exports.onChainChanged = onChainChanged;
    exports.refreshAccessToken = refreshAccessToken;
    exports.requestAccounts = requestAccounts;
    exports.requireProvider = requireProvider;
    exports.setAccessToken = setAccessToken;
    exports.signMessage = signMessage;
    exports.storeUcanRoot = storeUcanRoot;

}));
//# sourceMappingURL=web3-bs.umd.js.map
