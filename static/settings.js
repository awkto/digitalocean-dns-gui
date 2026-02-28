// Use relative URL so it works regardless of hostname/IP
const API_BASE_URL = '/api';

// Auth check — redirect to login if not authenticated
async function checkAuth() {
    try {
        const response = await fetch(`${API_BASE_URL}/auth/status`);
        const data = await response.json();
        if (!data.authenticated) {
            window.location.href = '/login.html';
            return false;
        }
        return true;
    } catch (error) {
        console.error('Auth check failed:', error);
        window.location.href = '/login.html';
        return false;
    }
}

// Wrap fetch to intercept 401 responses globally
const _originalFetch = window.fetch;
window.fetch = async function(...args) {
    const response = await _originalFetch.apply(this, args);
    if (response.status === 401) {
        const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
        if (!url.includes('/api/auth/')) {
            window.location.href = '/login.html';
        }
    }
    return response;
};

// DOM Elements
const settingsForm = document.getElementById('settingsForm');
const testConnectionBtn = document.getElementById('testConnectionBtn');
const loadingMessage = document.getElementById('loadingMessage');
const successMessage = document.getElementById('successMessage');
const errorMessage = document.getElementById('errorMessage');

const apiTokenInput = document.getElementById('apiToken');
const dnsZoneInput = document.getElementById('dnsZone');

const toggleSecretBtn = document.getElementById('toggleSecretBtn');
const eyeIcon = document.getElementById('eyeIcon');
const eyeOffIcon = document.getElementById('eyeOffIcon');

// Track if this is a first-time setup
let isSetupMode = false;

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    // Check authentication first
    const isAuthenticated = await checkAuth();
    if (!isAuthenticated) return;

    loadCurrentConfig();
    loadApiToken();

    settingsForm.addEventListener('submit', handleSaveConfig);
    testConnectionBtn.addEventListener('click', handleTestConnection);
    toggleSecretBtn.addEventListener('click', toggleSecretVisibility);

    // API token controls
    document.getElementById('toggleApiTokenBtn').addEventListener('click', toggleApiTokenVisibility);
    document.getElementById('copyApiTokenBtn').addEventListener('click', copyApiToken);
    document.getElementById('regenerateApiTokenBtn').addEventListener('click', regenerateApiToken);
});

// Toggle token visibility
function toggleSecretVisibility() {
    if (apiTokenInput.type === 'password') {
        apiTokenInput.type = 'text';
        eyeIcon.style.display = 'none';
        eyeOffIcon.style.display = 'block';
    } else {
        apiTokenInput.type = 'password';
        eyeIcon.style.display = 'block';
        eyeOffIcon.style.display = 'none';
    }
}

// Load current configuration
async function loadCurrentConfig() {
    try {
        showLoading(true);
        hideMessages();
        
        const response = await fetch(`${API_BASE_URL}/config`);
        const data = await response.json();
        
        if (response.ok) {
            // Check if any configuration is missing (SETUP MODE)
            const hasAnyConfig = data.api_token || data.dns_zone;
            
            isSetupMode = !hasAnyConfig;
            
            // Update UI based on setup mode
            const backNavigation = document.getElementById('backNavigation');
            const settingsDescription = document.getElementById('settingsDescription');
            
            if (isSetupMode) {
                // Hide back button in setup mode
                if (backNavigation) {
                    backNavigation.style.display = 'none';
                }
                // Update description for first-time setup
                if (settingsDescription) {
                    settingsDescription.innerHTML = '🚀 <strong>Welcome!</strong> Please configure your DigitalOcean credentials to get started.';
                }
            } else {
                // Show back button when configuration exists
                if (backNavigation) {
                    backNavigation.style.display = 'block';
                }
            }
            
            // Populate form with current config
            apiTokenInput.value = data.api_token || '';
            dnsZoneInput.value = data.dns_zone || '';
            
            // Make token field not required if it exists
            if (data.has_token) {
                apiTokenInput.required = false;
            }
        }
        
        showLoading(false);
    } catch (error) {
        showLoading(false);
        showError(`Failed to load configuration: ${error.message}`);
    }
}

// Test connection
async function handleTestConnection(e) {
    e.preventDefault();
    
    try {
        hideMessages();
        testConnectionBtn.disabled = true;
        testConnectionBtn.innerHTML = '<span>Testing...</span>';
        
        const config = getFormData();
        
        // Validate required fields
        if (!validateConfig(config)) {
            showError('Please fill in all required fields');
            return;
        }
        
        const response = await fetch(`${API_BASE_URL}/config/test`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(config),
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showSuccess(`✅ ${data.message}`);
        } else {
            showError(data.error || 'Connection test failed');
        }
    } catch (error) {
        showError(`Test failed: ${error.message}`);
    } finally {
        testConnectionBtn.disabled = false;
        testConnectionBtn.innerHTML = `
            <svg class="btn-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
            </svg>
            Test Connection
        `;
    }
}

// Save configuration
async function handleSaveConfig(e) {
    e.preventDefault();
    
    try {
        hideMessages();
        
        const config = getFormData();
        
        // Validate required fields
        if (!validateConfig(config)) {
            showError('Please fill in all required fields');
            return;
        }
        
        const response = await fetch(`${API_BASE_URL}/config`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(config),
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showSuccess(`✅ Configuration saved successfully! DNS Zone: ${data.zone}`);
            
            // Redirect to main page after 2 seconds
            setTimeout(() => {
                window.location.href = '/';
            }, 2000);
        } else {
            showError(data.error || 'Failed to save configuration');
        }
    } catch (error) {
        showError(`Save failed: ${error.message}`);
    }
}

// Helper functions
function getFormData() {
    return {
        api_token: apiTokenInput.value.trim(),
        dns_zone: dnsZoneInput.value.trim()
    };
}

function validateConfig(config) {
    return config.api_token && config.dns_zone;
}

function showLoading(show) {
    loadingMessage.style.display = show ? 'block' : 'none';
}

function showSuccess(message) {
    successMessage.textContent = message;
    successMessage.style.display = 'block';
    errorMessage.style.display = 'none';
    
    // Auto-hide after 10 seconds
    setTimeout(() => {
        successMessage.style.display = 'none';
    }, 10000);
}

function showError(message) {
    errorMessage.textContent = message;
    errorMessage.style.display = 'block';
    successMessage.style.display = 'none';
}

function hideMessages() {
    successMessage.style.display = 'none';
    errorMessage.style.display = 'none';
}

// --- API Token ---
let _apiTokenValue = '';

async function loadApiToken() {
    try {
        const res = await fetch(`${API_BASE_URL}/auth/api-token`);
        if (!res.ok) return;
        const data = await res.json();
        _apiTokenValue = data.api_token;
        document.getElementById('apiTokenDisplay').value = _apiTokenValue;
        document.getElementById('apiTokenSection').style.display = 'block';
    } catch {
        // non-critical, skip
    }
}

function toggleApiTokenVisibility() {
    const input = document.getElementById('apiTokenDisplay');
    const btn = document.getElementById('toggleApiTokenBtn');
    if (input.type === 'password') {
        input.type = 'text';
        btn.innerHTML = `
            <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"/>
            </svg>
            Hide`;
    } else {
        input.type = 'password';
        btn.innerHTML = `
            <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>
            </svg>
            Show`;
    }
}

async function copyApiToken() {
    if (!_apiTokenValue) return;
    try {
        await navigator.clipboard.writeText(_apiTokenValue);
        const btn = document.getElementById('copyApiTokenBtn');
        const original = btn.innerHTML;
        btn.innerHTML = `<svg class="btn-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
        </svg> Copied!`;
        setTimeout(() => { btn.innerHTML = original; }, 2000);
    } catch {
        showError('Could not copy to clipboard');
    }
}

async function regenerateApiToken() {
    if (!confirm('Regenerate the API token? Any existing scripts using the old token will stop working.')) return;
    try {
        const res = await fetch(`${API_BASE_URL}/auth/api-token/regenerate`, { method: 'POST' });
        if (!res.ok) throw new Error('Failed to regenerate');
        const data = await res.json();
        _apiTokenValue = data.api_token;
        document.getElementById('apiTokenDisplay').value = _apiTokenValue;
        // Reset to hidden
        document.getElementById('apiTokenDisplay').type = 'password';
        document.getElementById('toggleApiTokenBtn').innerHTML = `
            <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>
            </svg>
            Show`;
        showSuccess('API token regenerated successfully.');
    } catch {
        showError('Failed to regenerate API token');
    }
}
