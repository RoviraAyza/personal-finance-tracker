// CSV Import functionality

document.addEventListener('DOMContentLoaded', function() {
    setupDragAndDrop();
    setupFileInput();
});

function setupDragAndDrop() {
    const dropZone = document.getElementById('drop-zone');

    if (!dropZone) return;

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => {
            dropZone.classList.add('drag-over');
        });
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => {
            dropZone.classList.remove('drag-over');
        });
    });

    dropZone.addEventListener('drop', handleDrop);
}

function setupFileInput() {
    const fileInput = document.getElementById('file-input');
    if (fileInput) {
        fileInput.addEventListener('change', function() {
            if (this.files.length > 0) {
                handleFile(this.files[0]);
            }
        });
    }
}

function handleDrop(e) {
    const dt = e.dataTransfer;
    const files = dt.files;

    if (files.length > 0) {
        handleFile(files[0]);
    }
}

async function handleFile(file) {
    if (!file.name.endsWith('.csv')) {
        showToast('Please upload a CSV file', 'error');
        return;
    }

    if (file.size > 5 * 1024 * 1024) {
        showToast('File too large. Maximum size is 5MB', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/import/preview', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Upload failed');
        }

        showPreview(data);

    } catch (error) {
        showToast(error.message, 'error');
    }
}

function showPreview(data) {
    // Hide upload, show preview
    document.getElementById('upload-section').classList.add('d-none');
    document.getElementById('preview-section').classList.remove('d-none');

    // Stats
    const statsHtml = `
        <div class="row text-center">
            <div class="col-4">
                <div class="h4 mb-0">${data.total}</div>
                <small class="text-muted">Total Rows</small>
            </div>
            <div class="col-4">
                <div class="h4 mb-0 text-success">${data.new_count}</div>
                <small class="text-muted">New</small>
            </div>
            <div class="col-4">
                <div class="h4 mb-0 text-warning">${data.duplicate_count}</div>
                <small class="text-muted">Duplicates</small>
            </div>
        </div>
    `;
    document.getElementById('preview-stats').innerHTML = statsHtml;

    // Errors
    if (data.errors.length > 0) {
        const errorsHtml = `
            <div class="alert alert-warning">
                <strong>Parsing warnings:</strong>
                <ul class="mb-0 small">
                    ${data.errors.map(e => `<li>${e}</li>`).join('')}
                </ul>
            </div>
        `;
        document.getElementById('preview-errors').innerHTML = errorsHtml;
    } else {
        document.getElementById('preview-errors').innerHTML = '';
    }

    // Table
    const tableBody = document.getElementById('preview-table');
    let tableHtml = '';

    // New transactions
    data.transactions.forEach(t => {
        tableHtml += `
            <tr>
                <td>${t.date}</td>
                <td>${escapeHtml(t.description)}</td>
                <td class="text-end ${t.amount < 0 ? 'text-danger' : 'text-success'}">${t.amount.toFixed(2)}</td>
                <td><span class="badge bg-success">New</span></td>
            </tr>
        `;
    });

    // Duplicates
    data.duplicates.forEach(t => {
        tableHtml += `
            <tr class="table-warning">
                <td>${t.date}</td>
                <td>${escapeHtml(t.description)}</td>
                <td class="text-end">${t.amount.toFixed(2)}</td>
                <td><span class="badge bg-warning text-dark">Duplicate</span></td>
            </tr>
        `;
    });

    tableBody.innerHTML = tableHtml;

    // Enable/disable confirm button
    const confirmBtn = document.getElementById('confirm-btn');
    if (data.new_count === 0) {
        confirmBtn.disabled = true;
        confirmBtn.textContent = 'No new transactions to import';
    } else {
        confirmBtn.disabled = false;
        confirmBtn.textContent = `Import ${data.new_count} Transactions`;
    }
}

async function confirmImport() {
    try {
        const response = await fetch('/import/confirm', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Import failed');
        }

        // Show success
        document.getElementById('preview-section').classList.add('d-none');
        document.getElementById('success-section').classList.remove('d-none');
        document.getElementById('success-message').textContent =
            `Successfully imported ${data.imported} transactions.`;

    } catch (error) {
        showToast(error.message, 'error');
    }
}

function resetImport() {
    document.getElementById('upload-section').classList.remove('d-none');
    document.getElementById('preview-section').classList.add('d-none');
    document.getElementById('success-section').classList.add('d-none');
    document.getElementById('file-input').value = '';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
