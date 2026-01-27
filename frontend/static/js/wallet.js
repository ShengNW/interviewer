/**
 * Yeying 钱包集成（web3-bs）
 */

// 全局变量
let provider = null;
let currentAccount = null;
let authToken = null;

// SDK
const YeYingWeb3 = window.YeYingWeb3 || null;

// API 地址
const API_BASE = window.location.origin + '/api/v1';
const AUTH_BASE = `${API_BASE}/auth`;

// 本地存储 key
const TOKEN_KEY = 'auth_token';
const ADDRESS_KEY = 'wallet_address';

function ensureSdk() {
    if (!YeYingWeb3) {
        throw new Error('web3-bs SDK 未加载');
    }
}

/**
 * 获取钱包 Provider（EIP-6963 优先 YeYing）
 */
async function getWalletProvider() {
    ensureSdk();
    if (provider) return provider;

    provider = await YeYingWeb3.getProvider({
        timeoutMs: 3000,
        preferYeYing: true
    });

    return provider;
}

/**
 * 连接钱包获取账户
 */
async function connectWallet() {
    const walletProvider = await getWalletProvider();
    const accounts = await walletProvider.request({
        method: 'eth_requestAccounts'
    });

    if (Array.isArray(accounts) && accounts.length > 0) {
        currentAccount = accounts[0];
        return currentAccount;
    }
    throw new Error('未获取到账户');
}

/**
 * 完整登录流程（SIWE -> JWT）
 */
async function performWalletLogin() {
    ensureSdk();

    const walletProvider = await getWalletProvider();

    const loginResult = await YeYingWeb3.loginWithChallenge({
        provider: walletProvider,
        baseUrl: AUTH_BASE,
        tokenStorageKey: TOKEN_KEY,
        storeToken: true,
        credentials: 'include'
    });

    currentAccount = loginResult.address;
    authToken = loginResult.token;

    localStorage.setItem(ADDRESS_KEY, loginResult.address);

    return loginResult;
}

/**
 * 格式化地址显示
 */
function formatAddress(address) {
    if (!address) return '';
    return `${address.substring(0, 6)}...${address.substring(address.length - 4)}`;
}

/**
 * 更新 UI 显示
 */
function updateWalletUI(isConnected) {
    const connectBtn = document.getElementById('connectWalletBtn');
    const walletInfo = document.getElementById('walletInfo');
    const walletAddress = document.getElementById('walletAddress');

    // 未登录页面：只更新连接按钮状态
    if (connectBtn && isConnected && currentAccount) {
        return;
    }

    // 已登录页面：显示钱包地址
    if (walletAddress && currentAccount) {
        walletAddress.textContent = formatAddress(currentAccount);
    }
}

/**
 * 显示 Toast 提示
 */
function showToast(type, message) {
    if (window.YeyingInterviewer && window.YeyingInterviewer.showToast) {
        window.YeyingInterviewer.showToast(type, message);
    } else {
        alert(message);
    }
}

/**
 * 退出登录
 */
async function performLogout() {
    try {
        if (YeYingWeb3 && YeYingWeb3.logout) {
            await YeYingWeb3.logout({
                baseUrl: AUTH_BASE,
                tokenStorageKey: TOKEN_KEY,
                storeToken: true,
                credentials: 'include'
            });
        } else {
            await fetch(`${AUTH_BASE}/logout`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            localStorage.removeItem(TOKEN_KEY);
        }
    } catch (error) {
        console.error('调用退出接口失败:', error);
    }

    currentAccount = null;
    authToken = null;
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(ADDRESS_KEY);
}

/**
 * 页面加载时初始化
 */
$(document).ready(async function() {
    console.log('Yeying 钱包模块已加载 (web3-bs)');

    // 等待并检测钱包
    try {
        provider = await getWalletProvider();
        console.log('钱包检测完成');

        if (provider && provider.isYeYingWallet) {
            console.log('检测到 YeYing Wallet');
        } else if (provider && provider.isMetaMask) {
            console.log('检测到 MetaMask');
        }
    } catch (error) {
        console.warn('钱包检测失败:', error.message);
    }

    // 检查是否已登录
    const savedToken = localStorage.getItem(TOKEN_KEY);
    const savedAddress = localStorage.getItem(ADDRESS_KEY);
    if (savedToken && savedAddress) {
        authToken = savedToken;
        currentAccount = savedAddress;
        updateWalletUI(true);
        console.log('已恢复登录状态');
    }

    // 绑定连接钱包按钮
    $('#connectWalletBtn').on('click', async function() {
        const $btn = $(this);
        const originalHtml = $btn.html();

        try {
            // 显示加载状态
            $btn.prop('disabled', true);
            $btn.html('<span class="spinner-border spinner-border-sm me-1"></span>连接中...');

            // 执行登录
            await performWalletLogin();

            // 更新 UI
            updateWalletUI(true);
            showToast('success', '钱包连接成功！');

            // 触发登录成功事件（用于landing页面监听）
            $(document).trigger('wallet:login:success');

        } catch (error) {
            console.error('连接失败:', error);

            // 恢复按钮
            $btn.prop('disabled', false);
            $btn.html(originalHtml);

            // 显示错误
            let errorMsg = '连接失败，请重试';
            if (error.code === 4001) {
                errorMsg = '您拒绝了连接请求';
            } else if (error.message && error.message.includes('No wallet')) {
                errorMsg = '未找到钱包，请确保夜莺钱包已解锁';
            } else if (error.message && error.message.includes('timeout')) {
                errorMsg = '连接超时，请检查钱包是否正常运行';
            } else if (error.message) {
                errorMsg = error.message;
            }

            showToast('error', errorMsg);
        }
    });

    // 绑定退出按钮
    $('#logoutBtn').on('click', async function() {
        await performLogout();
        console.log('已退出登录');
        window.location.href = '/';
    });

    // 监听钱包事件
    if (provider && provider.on) {
        provider.on('accountsChanged', (accounts) => {
            console.log('账户已切换:', accounts);
            if (!accounts || accounts.length === 0) {
                performLogout().finally(() => {
                    window.location.href = '/';
                });
                return;
            }

            if (accounts[0] !== currentAccount) {
                console.log('检测到账户切换，需要重新登录');
                performLogout().finally(() => {
                    window.location.href = '/';
                });
            }
        });

        provider.on('chainChanged', (chainId) => {
            console.log('链已切换:', chainId);
            window.location.reload();
        });
    }
});

// 暴露到全局（用于调试）
window.walletDebug = {
    provider,
    currentAccount,
    authToken,
    getToken: () => authToken,
    getAddress: () => currentAccount
};
