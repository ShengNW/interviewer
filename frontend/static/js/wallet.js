/**
 * Yeying 钱包集成
 */

// 全局变量
let wallet = null;
let currentAccount = null;
let authToken = null;

// API 地址
const API_BASE = window.location.origin + '/api/v1';

/**
 * 等待钱包注入
 */
async function waitForWallet() {
    return new Promise((resolve, reject) => {
        if (typeof window.ethereum !== 'undefined') {
            console.log('钱包已就绪');
            resolve(window.ethereum);
            return;
        }

        console.log('等待钱包注入...');
        let attempts = 0;
        const maxAttempts = 50; // 5秒

        const interval = setInterval(() => {
            attempts++;
            if (typeof window.ethereum !== 'undefined') {
                clearInterval(interval);
                console.log('检测到钱包对象');
                resolve(window.ethereum);
            } else if (attempts >= maxAttempts) {
                clearInterval(interval);
                reject(new Error('未检测到夜莺钱包'));
            }
        }, 100);
    });
}

/**
 * 连接钱包获取账户
 */
async function connectWallet() {
    try {
        const accounts = await wallet.request({
            method: 'eth_requestAccounts'
        });

        if (accounts.length > 0) {
            currentAccount = accounts[0];
            return currentAccount;
        }
        throw new Error('未获取到账户');
    } catch (error) {
        throw error;
    }
}

/**
 * 完整登录流程
 */
async function performWalletLogin() {
    try {
        // 1. 连接钱包
        console.log('正在连接钱包...');
        const address = await connectWallet();
        console.log('连接成功:', address);

        // 2. 获取挑战
        console.log('正在获取登录挑战...');
        const challengeRes = await fetch(`${API_BASE}/auth/challenge`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                body: { address: address }
            })
        });

        if (!challengeRes.ok) {
            throw new Error(`获取挑战失败: ${challengeRes.status}`);
        }

        const challengeData = await challengeRes.json();
        if (!challengeData.body || !challengeData.body.result) {
            throw new Error('挑战数据格式错误');
        }

        const challenge = challengeData.body.result;
        console.log('获取挑战成功');

        // 3. 签名挑战
        console.log('请在钱包中签名...');
        const signature = await wallet.request({
            method: 'personal_sign',
            params: [challenge, address]
        });
        console.log('签名成功');

        // 4. 验证签名
        console.log('正在验证签名...');
        const verifyRes = await fetch(`${API_BASE}/auth/verify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                body: {
                    address: address,
                    signature: signature
                }
            })
        });

        if (!verifyRes.ok) {
            throw new Error(`验证失败: ${verifyRes.status}`);
        }

        const verifyData = await verifyRes.json();
        if (!verifyData.body || !verifyData.body.token) {
            throw new Error('验证响应格式错误');
        }

        authToken = verifyData.body.token;

        // 5. 保存 token
        localStorage.setItem('auth_token', authToken);
        localStorage.setItem('wallet_address', address);

        console.log('登录成功！');
        console.log('Token:', authToken);

        return { address, token: authToken };

    } catch (error) {
        console.error('登录失败:', error);
        throw error;
    }
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
        // 连接成功后会自动刷新页面，所以这里不需要特别处理
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
    // 使用现有的 toast 工具，或者简单的 alert
    if (window.YeyingInterviewer && window.YeyingInterviewer.showToast) {
        window.YeyingInterviewer.showToast(type, message);
    } else {
        alert(message);
    }
}

/**
 * 页面加载时初始化
 */
$(document).ready(async function() {
    console.log('Yeying 钱包模块已加载');

    // 等待并检测钱包
    try {
        wallet = await waitForWallet();
        console.log('钱包检测完成');

        if (wallet.isYeYingWallet) {
            console.log('检测到 YeYing Wallet');
        } else if (wallet.isMetaMask) {
            console.log('检测到 MetaMask');
        }
    } catch (error) {
        console.warn('钱包检测失败:', error.message);
    }

    // 检查是否已登录
    const savedToken = localStorage.getItem('auth_token');
    const savedAddress = localStorage.getItem('wallet_address');
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

        // 检查钱包是否就绪
        if (!wallet) {
            showToast('error', '未检测到夜莺钱包，请确保已安装并启用');
            return;
        }

        try {
            // 显示加载状态
            $btn.prop('disabled', true);
            $btn.html('<span class="spinner-border spinner-border-sm me-1"></span>连接中...');

            // 执行登录
            const result = await performWalletLogin();

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
            } else if (error.message && error.message.includes('Session expired')) {
                errorMsg = '钱包会话已过期，请重新解锁钱包后再试';
            } else if (error.message && error.message.includes('No wallet found')) {
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
        try {
            // 调用后端退出接口清除Cookie
            await fetch(`${API_BASE}/auth/logout`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
        } catch (error) {
            console.error('调用退出接口失败:', error);
        }

        // 清除本地登录状态
        currentAccount = null;
        authToken = null;
        localStorage.removeItem('auth_token');
        localStorage.removeItem('wallet_address');

        console.log('已退出登录');

        // 刷新页面回到landing页
        window.location.href = '/';
    });

    // 监听钱包事件
    if (wallet) {
        wallet.on('accountsChanged', (accounts) => {
            console.log('账户已切换:', accounts);
            if (accounts.length === 0) {
                // 断开连接 - 清除所有状态并刷新
                currentAccount = null;
                authToken = null;
                localStorage.removeItem('auth_token');
                localStorage.removeItem('wallet_address');

                // 调用后端清除Cookie
                fetch(`${API_BASE}/auth/logout`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                }).catch(err => console.error('清除Cookie失败:', err));

                // 刷新页面
                window.location.href = '/';
            } else if (accounts[0] !== currentAccount) {
                // 切换账户 - 需要重新登录
                console.log('检测到账户切换，需要重新登录');
                currentAccount = null;
                authToken = null;
                localStorage.removeItem('auth_token');
                localStorage.removeItem('wallet_address');

                // 调用后端清除Cookie
                fetch(`${API_BASE}/auth/logout`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                }).catch(err => console.error('清除Cookie失败:', err));

                // 刷新页面
                window.location.href = '/';
            }
        });

        wallet.on('chainChanged', (chainId) => {
            console.log('链已切换:', chainId);
            // 建议刷新页面
            window.location.reload();
        });
    }
});

// 暴露到全局（用于调试）
window.walletDebug = {
    wallet,
    currentAccount,
    authToken,
    getToken: () => authToken,
    getAddress: () => currentAccount
};
