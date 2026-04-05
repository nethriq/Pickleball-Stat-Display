/**
 * Nethriq Frontend Application
 * Role-aware SPA for players and attendants.
 */

const API_BASE = '/api';
const TOKEN_KEY = 'nethriq_auth_token';
const USER_KEY = 'nethriq_user';
const POLLING_INTERVAL = 5000;
const GLOBAL_PAGE_SIZE = 25;

let globalJobs = [];
let globalVisibleCount = GLOBAL_PAGE_SIZE;
let selectedPlayer = null;
let playerSearchDebounce = null;
let forcePasswordSetup = false;

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
    setTimeout(() => {
        const alert = document.getElementById(alertId);
        if (alert) alert.remove();
    }, 5000);
}

function formatDate(dateString) {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleString();
}

function formatBytes(bytes) {
    if (bytes === 0 || bytes === null || bytes === undefined) return 'N/A';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const index = Math.floor(Math.log(bytes) / Math.log(1024));
    const size = bytes / Math.pow(1024, index);
    return `${size.toFixed(1)} ${units[index]}`;
}

function getToken() {
    return localStorage.getItem(TOKEN_KEY);
}

function setToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
}

function clearToken() {
    localStorage.removeItem(TOKEN_KEY);
}

function setCurrentUser(user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
}

function getCurrentUser() {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;

    try {
        return JSON.parse(raw);
    } catch (error) {
        console.error('Failed to parse cached user:', error);
        return null;
    }
}

function clearCurrentUser() {
    localStorage.removeItem(USER_KEY);
}

function getRole() {
    const user = getCurrentUser();
    return user?.role || null;
}

function isStubUser() {
    const user = getCurrentUser();
    return !!user?.is_stub;
}

function isAuthenticated() {
    return !!getToken();
}

async function apiFetch(endpoint, options = {}) {
    const token = getToken();
    const headers = options.headers || {};

    if (token && !endpoint.includes('register') && !endpoint.includes('login')) {
        headers.Authorization = `Token ${token}`;
    }

    const response = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });
    if (!response.ok) {
        let errorMessage = `HTTP ${response.status}`;
        try {
            const data = await response.json();
            errorMessage = data.error || errorMessage;
        } catch (error) {
            // Ignore JSON parse errors here.
        }
        throw new Error(errorMessage);
    }

    return response.json();
}

function showPage(pageName) {
    document.querySelectorAll('.page-section').forEach((page) => {
        page.style.display = 'none';
    });

    const page = document.getElementById(`page-${pageName}`);
    if (page) {
        page.style.display = 'block';
    }
}

function updateNavbar() {
    const navbar = document.getElementById('main-navbar');
    if (navbar) {
        navbar.style.display = forcePasswordSetup ? 'none' : 'block';
    }

    const isAuth = isAuthenticated();
    const role = getRole();

    const navRegister = document.getElementById('nav-register');
    const navLogin = document.getElementById('nav-login');
    const navUpload = document.getElementById('nav-upload');
    const navJobs = document.getElementById('nav-jobs');
    const navGlobalDashboard = document.getElementById('nav-global-dashboard');
    const navNewMatch = document.getElementById('nav-new-match');
    const navLogout = document.getElementById('nav-logout');

    navRegister.style.display = isAuth ? 'none' : 'block';
    navLogin.style.display = isAuth ? 'none' : 'block';
    navLogout.style.display = isAuth ? 'block' : 'none';

    const isAttendant = role === 'attendant' || role === 'admin';
    navUpload.style.display = isAuth && !isAttendant ? 'block' : 'none';
    navJobs.style.display = isAuth && !isAttendant ? 'block' : 'none';
    navGlobalDashboard.style.display = isAuth && isAttendant ? 'block' : 'none';
    navNewMatch.style.display = isAuth && isAttendant ? 'block' : 'none';
}

function routeAfterLogin() {
    if (isStubUser()) {
        forcePasswordSetup = true;
        updateNavbar();
        showPage('set-password');
        return;
    }

    forcePasswordSetup = false;
    updateNavbar();
    const role = getRole();
    const isAttendant = role === 'attendant' || role === 'admin';
    if (isAttendant) {
        loadGlobalDashboard();
        showPage('global-dashboard');
    } else {
        loadAndShowJobs();
        showPage('jobs');
    }
}

async function registerUser(username, password, email) {
    const response = await apiFetch('/register/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, email }),
    });

    setToken(response.token);
    setCurrentUser(response);
    updateNavbar();
    showAlert('Registration successful. Redirecting...', 'success');
    setTimeout(() => routeAfterLogin(), 800);
}

async function loginUser(username, password) {
    const response = await apiFetch('/login/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
    });

    setToken(response.token);
    setCurrentUser(response);
    showAlert('Login successful. Redirecting...', 'success');
    setTimeout(() => routeAfterLogin(), 600);
}

async function verifyClaimToken(token) {
    const response = await apiFetch('/auth/claim-verify/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
    });

    setToken(response.token);
    setCurrentUser(response);
    forcePasswordSetup = !!response.is_stub;
    updateNavbar();
    return response;
}

async function setPasswordForClaim(newPassword) {
    const response = await apiFetch('/auth/set-password/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_password: newPassword }),
    });

    if (response.token) {
        setToken(response.token);
    }
    setCurrentUser(response);
    forcePasswordSetup = false;
    updateNavbar();
    return response;
}

function logoutUser() {
    clearToken();
    clearCurrentUser();
    selectedPlayer = null;
    updateNavbar();
    showPage('login');
    showAlert('Logged out successfully', 'success');
}

async function uploadVideo(file, name) {
    const formData = new FormData();
    formData.append('video_file', file);
    if (name) formData.append('name', name);

    const statusDiv = document.getElementById('upload-status');
    statusDiv.style.display = 'block';

    try {
        const response = await apiFetch('/upload/', {
            method: 'POST',
            body: formData,
        });

        showAlert('Video uploaded successfully!', 'success');
        document.getElementById('form-upload').reset();
        statusDiv.style.display = 'none';

        setTimeout(() => {
            loadAndShowJobs();
            showPage('jobs');
        }, 1200);

        return response;
    } catch (error) {
        statusDiv.style.display = 'none';
        showAlert(`Upload failed: ${error.message}`);
        throw error;
    }
}

async function uploadVideoAsAttendant(file, name, playerId) {
    const formData = new FormData();
    formData.append('video_file', file);
    if (name) formData.append('name', name);
    formData.append('player_id', String(playerId));

    try {
        const response = await apiFetch('/upload/', {
            method: 'POST',
            body: formData,
        });

        showAlert('Match uploaded. Redirecting to Global Dashboard...', 'success');
        document.getElementById('form-attendant-upload').reset();
        selectedPlayer = null;
        updateSelectedPlayerUI();
        clearPlayerSearchResults();

        setTimeout(() => {
            loadGlobalDashboard();
            showPage('global-dashboard');
        }, 800);

        return response;
    } catch (error) {
        if (error.message.toLowerCase().includes('invalid player_id')) {
            showAlert('Selected player is invalid. Please choose a player from the search list.', 'warning');
        } else {
            showAlert(`Upload failed: ${error.message}`);
        }
        throw error;
    }
}

async function getJobs() {
    try {
        const response = await apiFetch('/jobs/');
        return response.jobs || [];
    } catch (error) {
        showAlert(`Failed to load jobs: ${error.message}`);
        return [];
    }
}

async function getGlobalJobs() {
    const response = await apiFetch('/jobs/global/');
    return response.jobs || [];
}

async function getJobStatus(jobId) {
    return apiFetch(`/jobs/${jobId}/status/`);
}

async function searchPlayers(query) {
    const response = await apiFetch(`/players/search/?q=${encodeURIComponent(query)}`);
    return response.players || [];
}

async function createStubPlayer(name, email) {
    return apiFetch('/players/stub/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email }),
    });
}

async function resendClaimEmail(email) {
    return apiFetch('/auth/resend-claim/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
    });
}

async function downloadFileWithAuth(endpoint, filename) {
    const token = getToken();
    const headers = {};
    if (token) headers.Authorization = `Token ${token}`;

    const response = await fetch(`${API_BASE}${endpoint}`, { headers });
    if (!response.ok) {
        let errorMessage = `HTTP ${response.status}`;
        try {
            const data = await response.json();
            errorMessage = data.error || errorMessage;
        } catch (error) {
            // Ignore parse errors.
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

async function selectPlayer(jobId, playerIndex) {
    try {
        const response = await apiFetch(`/jobs/${jobId}/select-player/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ playerIndex }),
        });
        showAlert('Player selected. Processing started.', 'success');
        setTimeout(() => showJobDetails(jobId), 1000);
        return response;
    } catch (error) {
        showAlert(`Selection failed: ${error.message}`);
        throw error;
    }
}

function getStatusBadge(status) {
    const badges = {
        PENDING: '<span class="badge bg-secondary">Pending</span>',
        PROCESSING: '<span class="badge bg-info">Processing</span>',
        AWAITING_PLAYER_SELECTION: '<span class="badge bg-warning">Select Player</span>',
        COMPLETED: '<span class="badge bg-success">Completed</span>',
        FAILED: '<span class="badge bg-danger">Failed</span>',
    };
    return badges[status] || `<span class="badge bg-dark">${status}</span>`;
}

async function loadAndShowJobs() {
    const loadingDiv = document.getElementById('jobs-loading');
    const tableContainer = document.getElementById('jobs-table-container');
    const emptyDiv = document.getElementById('jobs-empty');
    const tableBody = document.getElementById('jobs-table-body');

    loadingDiv.style.display = 'block';
    tableContainer.style.display = 'none';
    emptyDiv.style.display = 'none';

    try {
        const jobs = await getJobs();
        if (jobs.length === 0) {
            loadingDiv.style.display = 'none';
            emptyDiv.style.display = 'block';
            return;
        }

        tableBody.innerHTML = '';
        jobs.forEach((job) => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${job.id}</td>
                <td>${job.name || job.filename}</td>
                <td>${getStatusBadge(job.status)}</td>
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

function renderGlobalJobsTable() {
    const tableBody = document.getElementById('global-jobs-table-body');
    const countText = document.getElementById('global-jobs-count');
    const loadMoreBtn = document.getElementById('global-load-more');

    const visibleJobs = globalJobs.slice(0, globalVisibleCount);
    tableBody.innerHTML = '';

    visibleJobs.forEach((job) => {
        const row = document.createElement('tr');
        const playerName = job.user__username || `User ${job.user_id}`;
        const uploaderName = job.uploader__username || 'Self';

        row.innerHTML = `
            <td>${formatDate(job.uploaded_at)}</td>
            <td>
                <div class="fw-semibold">${playerName}</div>
                <small class="text-muted">Uploader: ${uploaderName}</small>
            </td>
            <td>${job.name || job.filename || 'Untitled'}</td>
            <td>${getStatusBadge(job.status)}</td>
            <td>
                <button class="btn btn-sm btn-info" onclick="showJobDetails(${job.id})">View</button>
                ${job.status === 'COMPLETED' ? `<button class="btn btn-sm btn-success" onclick="showJobDetails(${job.id})">Downloads</button>` : ''}
            </td>
        `;
        tableBody.appendChild(row);
    });

    countText.textContent = `Showing ${visibleJobs.length} of ${globalJobs.length} jobs.`;
    loadMoreBtn.style.display = visibleJobs.length < globalJobs.length ? 'inline-block' : 'none';
}

async function loadGlobalDashboard() {
    const loadingDiv = document.getElementById('global-jobs-loading');
    const tableContainer = document.getElementById('global-jobs-table-container');
    const emptyDiv = document.getElementById('global-jobs-empty');

    loadingDiv.style.display = 'block';
    tableContainer.style.display = 'none';
    emptyDiv.style.display = 'none';

    try {
        globalJobs = await getGlobalJobs();
        globalVisibleCount = GLOBAL_PAGE_SIZE;

        if (globalJobs.length === 0) {
            loadingDiv.style.display = 'none';
            emptyDiv.style.display = 'block';
            return;
        }

        renderGlobalJobsTable();
        loadingDiv.style.display = 'none';
        tableContainer.style.display = 'block';
    } catch (error) {
        loadingDiv.style.display = 'none';
        loadingDiv.innerHTML = `<div class="alert alert-danger">Failed to load global dashboard: ${error.message}</div>`;
    }
}

function stopPollingJobStatus() {
    const modalElement = document.getElementById('jobDetailsModal');
    if (modalElement && modalElement.pollingIntervalId) {
        clearInterval(modalElement.pollingIntervalId);
        modalElement.pollingIntervalId = null;
    }
}

async function showJobDetails(jobId) {
    try {
        stopPollingJobStatus();
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
                <dd class="col-sm-9">${job.name || 'Untitled'}</dd>
                <dt class="col-sm-3">Status</dt>
                <dd class="col-sm-9">${getStatusBadge(job.status)}</dd>
                <dt class="col-sm-3">Uploaded</dt>
                <dd class="col-sm-9">${formatDate(job.uploaded_at)}</dd>
                <dt class="col-sm-3">Completed</dt>
                <dd class="col-sm-9">${formatDate(job.completed_at)}</dd>
                ${job.error_message ? `<dt class="col-sm-3">Error</dt><dd class="col-sm-9"><span class="text-danger">${job.error_message}</span></dd>` : ''}
            </dl>
        `;

        if (job.status === 'AWAITING_PLAYER_SELECTION' && job.thumbnail_urls && job.thumbnail_urls.length > 0) {
            detailsContent.innerHTML += `
                <div class="mt-4">
                    <h5 class="mb-3">Select Player for Processing</h5>
                    <div class="row g-3">
                        ${job.thumbnail_urls.map((thumb, displayIdx) => `
                            <div class="col-6 col-md-3">
                                <div class="card player-thumbnail" onclick="selectPlayer(${jobId}, ${thumb.playerIndex})" style="cursor:pointer;">
                                    <img src="${thumb.url}" class="card-img-top" alt="Player ${displayIdx + 1}">
                                    <div class="card-body text-center p-2">
                                        <small class="text-muted fw-bold">Player ${displayIdx + 1}</small>
                                        <div class="small text-muted">PBV ID ${thumb.playerIndex}</div>
                                    </div>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
            downloadsContainer.style.display = 'none';
            downloadAllBtn.style.display = 'none';
            pollingStatus.style.display = 'none';
        } else if (job.status === 'COMPLETED') {
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

        const modal = new bootstrap.Modal(document.getElementById('jobDetailsModal'));
        modal.show();
    } catch (error) {
        showAlert(`Failed to load job details: ${error.message}`);
    }
}

function startPollingJobStatus(jobId) {
    stopPollingJobStatus();
    const pollingIntervalId = setInterval(async () => {
        try {
            const job = await getJobStatus(jobId);
            document.getElementById('job-polling-text').textContent = job.status;

            if (job.status === 'AWAITING_PLAYER_SELECTION' || job.status === 'COMPLETED' || job.status === 'FAILED') {
                clearInterval(pollingIntervalId);
                showJobDetails(jobId);

                if (job.status === 'COMPLETED') {
                    showAlert('Job completed!', 'success');
                } else if (job.status === 'FAILED') {
                    showAlert('Job failed!', 'error');
                } else {
                    showAlert('Please select player to continue processing.', 'info');
                }
            }
        } catch (error) {
            console.error('Polling error:', error);
        }
    }, POLLING_INTERVAL);

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

    zipfiles.forEach((zipfile) => {
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

function clearPlayerSearchResults() {
    const results = document.getElementById('player-search-results');
    results.innerHTML = '';
}

function updateSelectedPlayerUI() {
    const selectedText = document.getElementById('selected-player-text');
    if (selectedPlayer) {
        selectedText.textContent = `Selected: ${selectedPlayer.name} (${selectedPlayer.email || selectedPlayer.username})`;
    } else {
        selectedText.textContent = 'No player selected.';
    }
}

function selectPlayerForUpload(player) {
    selectedPlayer = player;
    updateSelectedPlayerUI();
    clearPlayerSearchResults();
    document.getElementById('player-search').value = player.name;
}

function renderPlayerSearchResults(players) {
    const results = document.getElementById('player-search-results');
    results.innerHTML = '';

    if (!players.length) {
        results.innerHTML = '<div class="list-group-item">No players found</div>';
        return;
    }

    players.forEach((player) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'list-group-item list-group-item-action';
        button.textContent = `${player.name} (${player.email || player.username})`;
        button.addEventListener('click', () => selectPlayerForUpload(player));
        results.appendChild(button);
    });
}

function setupNavigationHandlers() {
    document.querySelectorAll('.navbar-nav a').forEach((link) => {
        link.addEventListener('click', (e) => {
            const href = link.getAttribute('href');

            if (forcePasswordSetup && href !== '#logout') {
                e.preventDefault();
                showPage('set-password');
                showAlert('Please set your password before continuing.', 'warning');
                return;
            }

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
            } else if (href === '#global-dashboard') {
                e.preventDefault();
                loadGlobalDashboard();
                showPage('global-dashboard');
            } else if (href === '#new-match') {
                e.preventDefault();
                showPage('new-match');
            } else if (href === '#register') {
                e.preventDefault();
                showPage('register');
            } else if (href === '#login') {
                e.preventDefault();
                showPage('login');
            }
        });
    });

    document.querySelectorAll('a[href="#new-match"]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            showPage('new-match');
        });
    });
}

function setupFormHandlers() {
    document.getElementById('form-login').addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('login-username').value;
        const password = document.getElementById('login-password').value;

        try {
            await loginUser(username, password);
        } catch (error) {
            showAlert(`Login failed: ${error.message}`);
        }
    });

    document.getElementById('form-register').addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('register-username').value;
        const password = document.getElementById('register-password').value;
        const email = document.getElementById('register-email').value;

        try {
            await registerUser(username, password, email);
        } catch (error) {
            showAlert(`Registration failed: ${error.message}`);
        }
    });

    document.getElementById('form-set-password').addEventListener('submit', async (e) => {
        e.preventDefault();
        const newPassword = document.getElementById('set-password-new').value;
        const confirmPassword = document.getElementById('set-password-confirm').value;

        if (newPassword !== confirmPassword) {
            showAlert('Passwords do not match.', 'warning');
            return;
        }

        try {
            await setPasswordForClaim(newPassword);
            showAlert('Password set successfully. Redirecting...', 'success');
            document.getElementById('form-set-password').reset();
            setTimeout(() => routeAfterLogin(), 500);
        } catch (error) {
            showAlert(`Could not set password: ${error.message}`);
        }
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

    document.getElementById('form-attendant-upload').addEventListener('submit', async (e) => {
        e.preventDefault();

        const file = document.getElementById('attendant-upload-file').files[0];
        const name = document.getElementById('attendant-upload-name').value;

        if (!selectedPlayer) {
            showAlert('Please select a player from search results before uploading.', 'warning');
            return;
        }

        if (!file) {
            showAlert('Please select a video file.', 'warning');
            return;
        }

        await uploadVideoAsAttendant(file, name, selectedPlayer.id);
    });

    document.getElementById('form-create-stub').addEventListener('submit', async (e) => {
        e.preventDefault();
        const name = document.getElementById('stub-name').value.trim();
        const email = document.getElementById('stub-email').value.trim();
        const resultBox = document.getElementById('stub-create-result');

        resultBox.innerHTML = '';

        try {
            const stub = await createStubPlayer(name, email);
            resultBox.innerHTML = `
                <div class="alert alert-success mb-0">
                    <div><strong>Stub created:</strong> ${stub.username}</div>
                    <div><strong>Temporary password:</strong> ${stub.temporary_password}</div>
                </div>
            `;

            const autoPlayer = {
                id: stub.player_id,
                username: stub.username,
                email: stub.email,
                name,
            };
            selectPlayerForUpload(autoPlayer);
            showAlert('Stub player created and selected for upload.', 'success');
            document.getElementById('form-create-stub').reset();
        } catch (error) {
            const lowerMessage = error.message.toLowerCase();
            if (lowerMessage.includes('already exists') || lowerMessage.includes('email')) {
                showAlert('A player with this email already exists. Please select them from the search list.', 'warning');
            } else {
                showAlert(`Failed to create stub player: ${error.message}`);
            }
        }
    });

    document.getElementById('form-resend-claim').addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('resend-claim-email').value.trim().toLowerCase();

        try {
            await resendClaimEmail(email);
            showAlert(`Claim email queued for ${email}.`, 'success');
            document.getElementById('form-resend-claim').reset();
        } catch (error) {
            showAlert(`Could not resend claim email: ${error.message}`);
        }
    });

    document.getElementById('player-search').addEventListener('input', (e) => {
        const query = e.target.value.trim();

        if (playerSearchDebounce) {
            clearTimeout(playerSearchDebounce);
        }

        if (query.length < 2) {
            clearPlayerSearchResults();
            return;
        }

        playerSearchDebounce = setTimeout(async () => {
            try {
                const players = await searchPlayers(query);
                renderPlayerSearchResults(players);
            } catch (error) {
                showAlert(`Player search failed: ${error.message}`);
            }
        }, 250);
    });

    document.getElementById('global-load-more').addEventListener('click', () => {
        globalVisibleCount += GLOBAL_PAGE_SIZE;
        renderGlobalJobsTable();
    });
}

async function checkHealth() {
    try {
        await apiFetch('/health/');
        return true;
    } catch (error) {
        console.error('Backend health check failed:', error);
        return false;
    }
}

async function processClaimLinkIfPresent() {
    const token = new URLSearchParams(window.location.search).get('token');
    const isClaimPath = window.location.pathname.startsWith('/claim');

    if (!isClaimPath || !token) {
        return false;
    }

    try {
        await verifyClaimToken(token);
        history.replaceState({}, '', '/');
        showAlert('Claim link verified. Please set your password to continue.', 'info');
        showPage('set-password');
        return true;
    } catch (error) {
        showAlert(`Claim link invalid: ${error.message}. Ask your attendant to resend your claim link.`, 'warning');
        clearToken();
        clearCurrentUser();
        forcePasswordSetup = false;
        updateNavbar();
        showPage('login');
        return true;
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    updateNavbar();
    setupNavigationHandlers();
    setupFormHandlers();

    const modalElement = document.getElementById('jobDetailsModal');
    if (modalElement) {
        modalElement.addEventListener('hidden.bs.modal', () => {
            stopPollingJobStatus();
        });
    }

    const handledClaim = await processClaimLinkIfPresent();
    if (handledClaim) {
        const healthy = await checkHealth();
        if (!healthy) {
            showAlert('Backend health check failed. Some actions may not work.', 'warning');
        }
        return;
    }

    if (isAuthenticated()) {
        forcePasswordSetup = isStubUser();
        routeAfterLogin();
    } else {
        showPage('login');
    }

    const healthy = await checkHealth();
    if (!healthy) {
        showAlert('Backend health check failed. Some actions may not work.', 'warning');
    }
});
