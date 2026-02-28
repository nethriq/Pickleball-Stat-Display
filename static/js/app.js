/**
 * Nethriq Frontend Application
 * Vanilla JavaScript with Bootstrap 5
 * API integration for video upload & job management
 */

// ============================================================================
// Configuration
// ============================================================================

const API_BASE = '/api';
const TOKEN_KEY = 'nethriq_auth_token';
const POLLING_INTERVAL = 5000; // 5 seconds

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Show an alert/notification to the user
 */
function showAlert(message, type = 'error') {
    const alertContainer = document.getElementById('alert-container');
    const alertId = 'alert-' + Date.now();
    
    const alertHtml = `
        <div id="${alertId}" class="alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    alertContainer.insertAdjacentHTML('beforeend', alertHtml);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        const alert = document.getElementById(alertId);
        if (alert) {
            alert.remove();
        }
    }, 5000);
}

/**
 * Format a date string to readable format
 */
function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleString();
}

/**
 * Format bytes to human readable size
 */
function formatBytes(bytes) {
    if (bytes === 0 || bytes === null || bytes === undefined) return 'N/A';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const index = Math.floor(Math.log(bytes) / Math.log(1024));
    const size = bytes / Math.pow(1024, index);
    return `${size.toFixed(1)} ${units[index]}`;
}

/**
 * Fetch helper with token authentication
 */
async function apiFetch(endpoint, options = {}) {
    const token = getToken();
    const headers = options.headers || {};
    
    // Add token to Authorization header for authenticated requests
    if (token && !endpoint.includes('register') && !endpoint.includes('login')) {
        headers['Authorization'] = `Token ${token}`;
    }
    
    const config = { ...options, headers };
    
    try {
        const response = await fetch(`${API_BASE}${endpoint}`, config);
        
        if (!response.ok) {
            let errorMessage = `HTTP ${response.status}`;
            try {
                const data = await response.json();
                errorMessage = data.error || errorMessage;
            } catch (e) {
                // Response wasn't JSON
            }
            throw new Error(errorMessage);
        }
        
        return await response.json();
    } catch (error) {
        console.error('API Error:', error);
        throw error;
    }
}

// ============================================================================
// Token Management
// ============================================================================

function getToken() {
    return localStorage.getItem(TOKEN_KEY);
}

function setToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
}

function clearToken() {
    localStorage.removeItem(TOKEN_KEY);
}

function isAuthenticated() {
    return !!getToken();
}

// ============================================================================
// Page Navigation
// ============================================================================

/**
 * Show only one page section
 */
function showPage(pageName) {
    // Hide all pages
    document.querySelectorAll('.page-section').forEach(page => {
        page.style.display = 'none';
    });
    
    // Show selected page
    const page = document.getElementById(`page-${pageName}`);
    if (page) {
        page.style.display = 'block';
    }
    
    // Update active nav item
    document.querySelectorAll('.navbar-nav .nav-link').forEach(link => {
        link.classList.remove('active');
    });
    
    console.log(`Showing page: ${pageName}`);
}

/**
 * Update navbar based on authentication state
 */
function updateNavbar() {
    const isAuth = isAuthenticated();
    
    document.getElementById('nav-register').style.display = isAuth ? 'none' : 'block';
    document.getElementById('nav-login').style.display = isAuth ? 'none' : 'block';
    document.getElementById('nav-upload').style.display = isAuth ? 'block' : 'none';
    document.getElementById('nav-jobs').style.display = isAuth ? 'block' : 'none';
    document.getElementById('nav-logout').style.display = isAuth ? 'block' : 'none';
}

// ============================================================================
// Authentication Functions
// ============================================================================

/**
 * Register a new user
 */
async function registerUser(username, password, email) {
    try {
        const response = await apiFetch('/register/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, email })
        });
        
        setToken(response.token);
        updateNavbar();
        showAlert('Registration successful! Redirecting to login...', 'success');
        setTimeout(() => showPage('login'), 1500);
        return response;
    } catch (error) {
        showAlert(`Registration failed: ${error.message}`);
        throw error;
    }
}

/**
 * Login user
 */
async function loginUser(username, password) {
    try {
        const response = await apiFetch('/login/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        
        setToken(response.token);
        updateNavbar();
        showAlert('Login successful! Redirecting...', 'success');
        setTimeout(() => showPage('upload'), 1500);
        return response;
    } catch (error) {
        showAlert(`Login failed: ${error.message}`);
        throw error;
    }
}

/**
 * Logout user
 */
function logoutUser() {
    clearToken();
    updateNavbar();
    showPage('login');
    showAlert('Logged out successfully', 'success');
}

// ============================================================================
// Video Upload Functions
// ============================================================================

/**
 * Upload video file
 */
async function uploadVideo(file, name) {
    try {
        const formData = new FormData();
        formData.append('video_file', file);
        if (name) {
            formData.append('name', name);
        }
        
        // Show upload status
        const statusDiv = document.getElementById('upload-status');
        statusDiv.style.display = 'block';
        
        const response = await apiFetch('/upload/', {
            method: 'POST',
            body: formData
        });
        
        showAlert('Video uploaded successfully!', 'success');
        
        // Reset form
        document.getElementById('form-upload').reset();
        statusDiv.style.display = 'none';
        
        // Redirect to jobs page after 2 seconds
        setTimeout(() => {
            loadAndShowJobs();
            showPage('jobs');
        }, 2000);
        
        return response;
    } catch (error) {
        document.getElementById('upload-status').style.display = 'none';
        showAlert(`Upload failed: ${error.message}`);
        throw error;
    }
}

// ============================================================================
// Job Management Functions
// ============================================================================

/**
 * Get list of jobs
 */
async function getJobs() {
    try {
        const response = await apiFetch('/jobs/');
        return response.jobs || [];
    } catch (error) {
        showAlert(`Failed to load jobs: ${error.message}`);
        return [];
    }
}

/**
 * Get job details and status
 */
async function getJobStatus(jobId) {
    try {
        const response = await apiFetch(`/jobs/${jobId}/status/`);
        return response;
    } catch (error) {
        showAlert(`Failed to load job status: ${error.message}`);
        throw error;
    }
}

/**
 * Download job results
 */
async function downloadJobResults(jobId) {
    try {
        const response = await apiFetch(`/jobs/${jobId}/download/`);
        const deliverables = response.deliverables;
        if (!deliverables || !deliverables.master_zip) {
            showAlert('No downloadable zipfiles available', 'warning');
            return;
        }
        await downloadAllZip(jobId, deliverables.master_zip.name);
    } catch (error) {
        showAlert(`Download failed: ${error.message}`);
        throw error;
    }
}

/**
 * Download zipfile with auth via fetch
 */
async function downloadFileWithAuth(endpoint, filename) {
    const token = getToken();
    const headers = {};
    if (token) {
        headers['Authorization'] = `Token ${token}`;
    }

    const response = await fetch(`${API_BASE}${endpoint}`, { headers });
    if (!response.ok) {
        let errorMessage = `HTTP ${response.status}`;
        try {
            const data = await response.json();
            errorMessage = data.error || errorMessage;
        } catch (e) {
            // Response wasn't JSON
        }
        throw new Error(errorMessage);
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename || 'download.zip';
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
}

async function downloadZipFile(jobId, zipId, filename) {
    await downloadFileWithAuth(`/jobs/${jobId}/download-zip/${encodeURIComponent(zipId)}/`, filename);
    showAlert('Download started!', 'success');
}

async function downloadAllZip(jobId, filename) {
    await downloadFileWithAuth(`/jobs/${jobId}/download-all/`, filename);
    showAlert('Download started!', 'success');
}

/**
 * Load and display jobs in the table
 */
async function loadAndShowJobs() {
    const loadingDiv = document.getElementById('jobs-loading');
    const tableContainer = document.getElementById('jobs-table-container');
    const emptyDiv = document.getElementById('jobs-empty');
    const tableBody = document.getElementById('jobs-table-body');
    
    try {
        loadingDiv.style.display = 'block';
        tableContainer.style.display = 'none';
        emptyDiv.style.display = 'none';
        
        const jobs = await getJobs();
        
        if (jobs.length === 0) {
            loadingDiv.style.display = 'none';
            emptyDiv.style.display = 'block';
            return;
        }
        
        tableBody.innerHTML = '';
        jobs.forEach(job => {
            const row = document.createElement('tr');
            const statusBadge = getStatusBadge(job.status);
            
            row.innerHTML = `
                <td>${job.id}</td>
                <td>${job.name || job.filename}</td>
                <td>${statusBadge}</td>
                <td>${formatDate(job.uploaded_at)}</td>
                <td>
                    <button class="btn btn-sm btn-info" onclick="showJobDetails(${job.id})">View</button>
                    ${job.status === 'COMPLETED' ? `<button class="btn btn-sm btn-success" onclick="showJobDetails(${job.id})">Downloads</button>` : ''}
                </td>
            `;
            
            tableBody.appendChild(row);
        });
        
        loadingDiv.style.display = 'none';
        tableContainer.style.display = 'block';
    } catch (error) {
        loadingDiv.style.display = 'none';
        loadingDiv.innerHTML = '<div class="alert alert-danger">Failed to load jobs</div>';
    }
}

/**
 * Get HTML badge for job status
 */
function getStatusBadge(status) {
    const badges = {
        'PENDING': '<span class="badge bg-secondary">Pending</span>',
        'PROCESSING': '<span class="badge bg-info">Processing</span>',
        'COMPLETED': '<span class="badge bg-success">Completed</span>',
        'FAILED': '<span class="badge bg-danger">Failed</span>'
    };
    return badges[status] || `<span class="badge bg-dark">${status}</span>`;
}

/**
 * Show job details in modal and start polling
 */
async function showJobDetails(jobId) {
    try {
        const job = await getJobStatus(jobId);
        const detailsContent = document.getElementById('job-details-content');
        const downloadAllBtn = document.getElementById('job-download-all-btn');
        const downloadsContainer = document.getElementById('job-downloads');
        const pollingStatus = document.getElementById('job-polling-status');
        
        detailsContent.innerHTML = `
            <dl class="row">
                <dt class="col-sm-3">Job ID</dt>
                <dd class="col-sm-9">${job.id}</dd>
                
                <dt class="col-sm-3">Name</dt>
                <dd class="col-sm-9">${job.name}</dd>
                
                <dt class="col-sm-3">Status</dt>
                <dd class="col-sm-9">${getStatusBadge(job.status)}</dd>
                
                <dt class="col-sm-3">Uploaded</dt>
                <dd class="col-sm-9">${formatDate(job.uploaded_at)}</dd>
                
                <dt class="col-sm-3">Completed</dt>
                <dd class="col-sm-9">${formatDate(job.completed_at)}</dd>
                
                ${job.error_message ? `
                    <dt class="col-sm-3">Error</dt>
                    <dd class="col-sm-9"><span class="text-danger">${job.error_message}</span></dd>
                ` : ''}
            </dl>
        `;
        
        // Show download button if completed
        if (job.status === 'COMPLETED') {
            downloadsContainer.style.display = 'block';
            await loadDeliverables(jobId);
            downloadAllBtn.style.display = 'inline-block';
            pollingStatus.style.display = 'none';
        } else {
            downloadsContainer.style.display = 'none';
            downloadAllBtn.style.display = 'none';
            pollingStatus.style.display = 'block';
            startPollingJobStatus(jobId);
        }
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('jobDetailsModal'));
        modal.show();
    } catch (error) {
        showAlert(`Failed to load job details: ${error.message}`);
    }
}

/**
 * Poll job status and update modal
 */
function startPollingJobStatus(jobId) {
    const pollingIntervalId = setInterval(async () => {
        try {
            const job = await getJobStatus(jobId);
            document.getElementById('job-polling-text').textContent = job.status;
            
            if (job.status === 'COMPLETED' || job.status === 'FAILED') {
                clearInterval(pollingIntervalId);
                
                // Update view
                const downloadAllBtn = document.getElementById('job-download-all-btn');
                const downloadsContainer = document.getElementById('job-downloads');
                const pollingStatus = document.getElementById('job-polling-status');
                
                if (job.status === 'COMPLETED') {
                    downloadsContainer.style.display = 'block';
                    await loadDeliverables(jobId);
                    downloadAllBtn.style.display = 'inline-block';
                    showAlert('Job completed!', 'success');
                } else {
                    showAlert('Job failed!', 'error');
                }
                
                pollingStatus.style.display = 'none';
            }
        } catch (error) {
            console.error('Polling error:', error);
        }
    }, POLLING_INTERVAL);
    
    // Store interval ID on modal for cleanup if needed
    document.getElementById('jobDetailsModal').pollingIntervalId = pollingIntervalId;
}

async function loadDeliverables(jobId) {
    const downloadsList = document.getElementById('job-downloads-list');
    const downloadAllBtn = document.getElementById('job-download-all-btn');
    downloadsList.innerHTML = '';

    const response = await apiFetch(`/jobs/${jobId}/download/`);
    const deliverables = response.deliverables || {};
    const zipfiles = deliverables.zipfiles || [];

    if (!zipfiles.length) {
        downloadsList.innerHTML = '<div class="text-muted">No zipfiles available.</div>';
        downloadAllBtn.style.display = 'none';
        return;
    }

    zipfiles.forEach(zipfile => {
        const listItem = document.createElement('div');
        listItem.className = 'd-flex align-items-center justify-content-between border rounded px-2 py-2 mb-2';
        listItem.innerHTML = `
            <div>
                <div class="fw-semibold">${zipfile.name}</div>
                <div class="text-muted small">${formatBytes(zipfile.size)}</div>
            </div>
            <button class="btn btn-sm btn-outline-success">Download</button>
        `;
        const button = listItem.querySelector('button');
        button.addEventListener('click', async () => {
            try {
                await downloadZipFile(jobId, zipfile.id, zipfile.name);
            } catch (error) {
                showAlert(`Download failed: ${error.message}`);
            }
        });
        downloadsList.appendChild(listItem);
    });

    if (deliverables.master_zip && deliverables.master_zip.name) {
        downloadAllBtn.style.display = 'inline-block';
        downloadAllBtn.onclick = async () => {
            try {
                await downloadAllZip(jobId, deliverables.master_zip.name);
            } catch (error) {
                showAlert(`Download failed: ${error.message}`);
            }
        };
    } else {
        downloadAllBtn.style.display = 'none';
    }
}

// ============================================================================
// Event Listeners (Page Load & Form Submissions)
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('App initialized');
    
    // Update navbar on load
    updateNavbar();
    
    // Show appropriate page based on auth state
    if (isAuthenticated()) {
        showPage('upload');
    } else {
        showPage('login');
    }
    
    // ========================================================================
    // Navigation Click Handlers
    // ========================================================================
    
    document.querySelectorAll('.navbar-nav a').forEach(link => {
        link.addEventListener('click', (e) => {
            const href = link.getAttribute('href');
            
            if (href === '#logout') {
                e.preventDefault();
                logoutUser();
            } else if (href === '#upload') {
                e.preventDefault();
                showPage('upload');
            } else if (href === '#jobs') {
                e.preventDefault();
                loadAndShowJobs();
                showPage('jobs');
            } else if (href === '#register') {
                e.preventDefault();
                showPage('register');
            } else if (href === '#login') {
                e.preventDefault();
                showPage('login');
            }
        });
    });
    
    // ========================================================================
    // Form Submissions
    // ========================================================================
    
    document.getElementById('form-login').addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('login-username').value;
        const password = document.getElementById('login-password').value;
        
        await loginUser(username, password);
    });
    
    document.getElementById('form-register').addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('register-username').value;
        const password = document.getElementById('register-password').value;
        const email = document.getElementById('register-email').value;
        
        await registerUser(username, password, email);
    });
    
    document.getElementById('form-upload').addEventListener('submit', async (e) => {
        e.preventDefault();
        const file = document.getElementById('upload-file').files[0];
        const name = document.getElementById('upload-name').value;
        
        if (!file) {
            showAlert('Please select a file');
            return;
        }
        
        await uploadVideo(file, name);
    });
    
    // ========================================================================
    // Home/Register Navigation
    // ========================================================================
    
    // Handle navigation to login from anywhere
    const loginLinks = document.querySelectorAll('a[href="#login"]');
    console.log(`Found ${loginLinks.length} login links`);
    loginLinks.forEach((link, index) => {
        console.log(`Attaching listener to login link ${index}:`, link);
        link.addEventListener('click', (e) => {
            console.log('Login link clicked!');
            e.preventDefault();
            showPage('login');
        });
    });
    
    // Handle navigation to register from anywhere
    const registerLinks = document.querySelectorAll('a[href="#register"]');
    console.log(`Found ${registerLinks.length} register links`);
    registerLinks.forEach((link, index) => {
        console.log(`Attaching listener to register link ${index}:`, link);
        link.addEventListener('click', (e) => {
            console.log('Register link clicked!');
            e.preventDefault();
            showPage('register');
        });
    });
    
    console.log('All event listeners attached');
});

// ============================================================================
// Health Check (Optional - for debugging)
// ============================================================================

async function checkHealth() {
    try {
        const response = await apiFetch('/health/');
        console.log('Backend health:', response);
        return true;
    } catch (error) {
        console.error('Backend health check failed:', error);
        return false;
    }
}

// Check backend health on load
document.addEventListener('DOMContentLoaded', () => {
    checkHealth().then(healthy => {
        if (!healthy) {
            console.warn('Backend may be unavailable');
        }
    });
});
