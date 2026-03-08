const API_BASE_URL = '/api';

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
        window.location.href = '/login.html';
        return false;
    }
}

const _originalFetch = window.fetch;
window.fetch = async function(...args) {
    const response = await _originalFetch.apply(this, args);
    if (response.status === 401) {
        const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
        if (!url.includes('/api/auth/')) window.location.href = '/login.html';
    }
    return response;
};

async function handleLogout() {
    await fetch(`${API_BASE_URL}/auth/logout`, { method: 'POST' });
    window.location.href = '/login.html';
}

function toggleDarkMode() {
    document.body.classList.toggle('dark-mode');
    localStorage.setItem('theme', document.body.classList.contains('dark-mode') ? 'dark' : 'light');
}

const zoneName = document.getElementById('zoneName');
const recordCount = document.getElementById('recordCount');
const recordsTableBody = document.getElementById('recordsTableBody');
const loadingIndicator = document.getElementById('loadingIndicator');
const errorMessage = document.getElementById('errorMessage');
const addRecordForm = document.getElementById('addRecordForm');
const refreshBtn = document.getElementById('refreshBtn');
const editModal = document.getElementById('editModal');
const editRecordForm = document.getElementById('editRecordForm');
const cancelEditBtn = document.getElementById('cancelEditBtn');
const addModal = document.getElementById('addModal');
const addRecordBtn = document.getElementById('addRecordBtn');
const cancelAddBtn = document.getElementById('cancelAddBtn');
const searchInput = document.getElementById('searchInput');
const resultsCount = document.getElementById('resultsCount');
const typeFilters = document.getElementById('typeFilters');
const selectAllBtn = document.getElementById('selectAllBtn');
const deselectAllBtn = document.getElementById('deselectAllBtn');

let allRecords = [];
let selectedTypes = new Set();

async function checkConfigStatus() {
    try {
        const response = await fetch(`${API_BASE_URL}/config/status`);
        const data = await response.json();
        if (!data.configured) {
            window.location.href = '/settings.html';
            return false;
        }
        return true;
    } catch (error) {
        return false;
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    if (localStorage.getItem('theme') === 'dark') document.body.classList.add('dark-mode');

    const isAuthenticated = await checkAuth();
    if (!isAuthenticated) return;

    const urlParams = new URLSearchParams(window.location.search);
    const qParam = urlParams.get('q');
    if (qParam) searchInput.value = qParam;

    window.addEventListener('popstate', (event) => {
        searchInput.value = event.state?.q ?? new URLSearchParams(window.location.search).get('q') ?? '';
        applyFilters();
    });

    document.getElementById('logoutBtn').addEventListener('click', handleLogout);

    const isConfigured = await checkConfigStatus();
    if (!isConfigured) return;

    loadRecords();

    addRecordForm.addEventListener('submit', handleAddRecord);
    editRecordForm.addEventListener('submit', handleEditRecord);
    refreshBtn.addEventListener('click', loadRecords);
    addRecordBtn.addEventListener('click', showAddModal);
    cancelEditBtn.addEventListener('click', hideEditModal);
    cancelAddBtn.addEventListener('click', hideAddModal);
    selectAllBtn.addEventListener('click', selectAllFilters);
    deselectAllBtn.addEventListener('click', deselectAllFilters);
    searchInput.addEventListener('input', applyFilters);

    document.querySelectorAll('.close').forEach(closeBtn => {
        closeBtn.addEventListener('click', function() {
            const modal = this.closest('.modal');
            if (modal) modal.classList.remove('active');
        });
    });

    document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
        backdrop.addEventListener('click', function() {
            const modal = this.closest('.modal');
            if (modal) modal.classList.remove('active');
        });
    });
});

async function loadRecords() {
    try {
        showLoading(true);
        hideError();
        const response = await fetch(`${API_BASE_URL}/records`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || `HTTP error! status: ${response.status}`);
        zoneName.textContent = data.zone;
        allRecords = data.records;
        buildTypeFilters();
        applyFilters();
        showLoading(false);
    } catch (error) {
        showError(`Failed to load records: ${error.message}`);
        showLoading(false);
    }
}

function displayRecords(records) {
    recordsTableBody.innerHTML = '';
    if (records.length === 0) {
        recordsTableBody.innerHTML = '<tr><td colspan="5" class="status-message">No records found</td></tr>';
        return;
    }
    records.forEach(record => {
        const row = document.createElement('tr');
        const isProtected = (record.name === '@' && (record.type === 'NS' || record.type === 'SOA'));
        const disabled = isProtected ? 'btn-disabled' : '';
        const valuesHtml = record.values.map(val => escapeHtml(val)).join('<br>');
        row.innerHTML = `
            <td>
                <div class="record-name">${escapeHtml(record.name)}</div>
                <div class="record-fqdn">${escapeHtml(record.fqdn)}</div>
            </td>
            <td><span class="type-badge type-badge-${escapeHtml(record.type)}">${escapeHtml(record.type)}</span></td>
            <td class="tabular-nums">${record.ttl}s</td>
            <td class="record-values">${valuesHtml}</td>
            <td class="col-actions">
                <div class="actions-group">
                    <button class="btn-table-action ${disabled}" ${isProtected ? 'disabled' : ''}
                            onclick="editRecord('${escapeHtml(record.name)}', '${escapeHtml(record.type)}', ${record.ttl}, ${JSON.stringify(record.values).replace(/"/g, '&quot;')}, ${record.id})">
                        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg>
                        Edit
                    </button>
                    <button class="btn-table-action btn-table-delete ${disabled}" ${isProtected ? 'disabled' : ''}
                            onclick="deleteRecord('${escapeHtml(record.name)}', '${escapeHtml(record.type)}', ${record.id})">
                        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                        Delete
                    </button>
                </div>
            </td>
        `;
        recordsTableBody.appendChild(row);
    });
}

function buildTypeFilters() {
    const types = [...new Set(allRecords.map(r => r.type))].sort();
    typeFilters.innerHTML = '';
    types.forEach(type => {
        const button = document.createElement('button');
        button.className = 'filter-chip filter-chip-active';
        button.dataset.type = type;
        button.innerHTML = `<span class="type-badge type-badge-${type}">${type}</span>`;
        button.addEventListener('click', () => {
            if (selectedTypes.has(type)) { selectedTypes.delete(type); button.classList.remove('filter-chip-active'); }
            else { selectedTypes.add(type); button.classList.add('filter-chip-active'); }
            applyFilters();
        });
        typeFilters.appendChild(button);
        selectedTypes.add(type);
    });
}

async function handleAddRecord(e) {
    e.preventDefault();
    const name = document.getElementById('recordName').value.trim();
    const type = document.getElementById('recordType').value;
    const ttl = parseInt(document.getElementById('recordTTL').value);
    const values = document.getElementById('recordValues').value.trim().split('\n').map(v => v.trim()).filter(v => v);
    if (!values.length) { showError('Please enter at least one value'); return; }
    try {
        const response = await fetch(`${API_BASE_URL}/records`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, type, ttl, values }) });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to create record');
        showSuccess('Record created successfully!');
        addRecordForm.reset();
        hideAddModal();
        loadRecords();
    } catch (error) { showError(`Failed to create record: ${error.message}`); }
}

function editRecord(name, type, ttl, values, id) {
    document.getElementById('editRecordName').value = name;
    document.getElementById('editRecordType').value = type;
    document.getElementById('editRecordId').value = id;
    document.getElementById('editRecordTypeDisplay').value = type;
    document.getElementById('editRecordTTL').value = ttl;
    document.getElementById('editRecordValues').value = values.join('\n');
    editModal.classList.add('active');
}

async function handleEditRecord(e) {
    e.preventDefault();
    const newName = document.getElementById('editRecordName').value.trim();
    const type = document.getElementById('editRecordType').value;
    const id = document.getElementById('editRecordId').value;
    const ttl = parseInt(document.getElementById('editRecordTTL').value);
    const values = document.getElementById('editRecordValues').value.trim().split('\n').map(v => v.trim()).filter(v => v);
    if (!newName) { showError('Please enter a record name'); return; }
    if (!values.length) { showError('Please enter at least one value'); return; }
    try {
        const response = await fetch(`${API_BASE_URL}/records/${type}/${newName}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ttl, values, id, name: newName }) });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to update record');
        showSuccess('Record updated successfully!');
        hideEditModal();
        loadRecords();
    } catch (error) { showError(`Failed to update record: ${error.message}`); }
}

async function deleteRecord(name, type, id) {
    if (!confirm(`Delete the ${type} record "${name}"?`)) return;
    try {
        const response = await fetch(`${API_BASE_URL}/records/${type}/${name}?id=${id}`, { method: 'DELETE' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to delete record');
        showSuccess('Record deleted successfully!');
        loadRecords();
    } catch (error) { showError(`Failed to delete record: ${error.message}`); }
}

function hideEditModal() { editModal.classList.remove('active'); }
function showAddModal() { addModal.classList.add('active'); }
function hideAddModal() { addModal.classList.remove('active'); }

function showLoading(show) { loadingIndicator.style.display = show ? 'block' : 'none'; }

function showError(message) {
    errorMessage.textContent = message;
    errorMessage.style.display = 'block';
    setTimeout(() => { errorMessage.style.display = 'none'; }, 5000);
}

function hideError() { errorMessage.style.display = 'none'; }

function showSuccess(message) {
    const div = document.createElement('div');
    div.className = 'success';
    div.textContent = message;
    const container = document.querySelector('.content-container');
    container.insertBefore(div, container.firstChild);
    setTimeout(() => div.remove(), 3000);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function selectAllFilters() {
    document.querySelectorAll('.filter-chip').forEach(chip => { chip.classList.add('filter-chip-active'); if (chip.dataset.type) selectedTypes.add(chip.dataset.type); });
    applyFilters();
}

function deselectAllFilters() {
    document.querySelectorAll('.filter-chip').forEach(chip => { chip.classList.remove('filter-chip-active'); if (chip.dataset.type) selectedTypes.delete(chip.dataset.type); });
    applyFilters();
}

function updateUrlState() {
    const searchTerm = searchInput.value.trim();
    const url = new URL(window.location);
    if (searchTerm) url.searchParams.set('q', searchTerm);
    else url.searchParams.delete('q');
    history.replaceState({ q: searchTerm }, '', url);
}

function applyFilters() {
    const searchTerm = searchInput.value.toLowerCase().trim();
    updateUrlState();
    const filtered = allRecords.filter(record => {
        if (!selectedTypes.has(record.type)) return false;
        if (searchTerm) {
            const text = [record.name, record.type, record.fqdn, record.ttl.toString(), ...record.values].join(' ').toLowerCase();
            if (!text.includes(searchTerm)) return false;
        }
        return true;
    });
    recordCount.textContent = `${allRecords.length} records`;
    resultsCount.textContent = `${filtered.length} ${filtered.length === 1 ? 'Record' : 'Records'}`;
    displayRecords(filtered);
}