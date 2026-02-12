// Transactions page functionality

let selectedTransactions = new Set();
let currentSort = { column: 'date', direction: 'desc' };

// ==================== SORTING ====================

function sortTable(column) {
    const table = document.querySelector('.table tbody');
    const rows = Array.from(table.querySelectorAll('tr[data-id]'));

    if (rows.length === 0) return;

    // Toggle direction if same column, otherwise default to asc
    if (currentSort.column === column) {
        currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
    } else {
        currentSort.column = column;
        currentSort.direction = 'asc';
    }

    // Update header icons
    document.querySelectorAll('.sortable').forEach(th => {
        const icon = th.querySelector('.sort-icon');
        if (th.dataset.sort === column) {
            icon.textContent = currentSort.direction === 'asc' ? '↑' : '↓';
            th.classList.add('sorted');
        } else {
            icon.textContent = '↕';
            th.classList.remove('sorted');
        }
    });

    // Sort rows
    rows.sort((a, b) => {
        let aVal, bVal;

        switch (column) {
            case 'date':
                // Parse date from DD/MM/YYYY format
                const aDate = a.cells[1].textContent.split('/').reverse().join('-');
                const bDate = b.cells[1].textContent.split('/').reverse().join('-');
                aVal = new Date(aDate);
                bVal = new Date(bDate);
                break;
            case 'description':
                aVal = a.cells[2].textContent.toLowerCase();
                bVal = b.cells[2].textContent.toLowerCase();
                break;
            case 'amount':
                aVal = parseFloat(a.cells[3].textContent.replace(/[^\d.-]/g, ''));
                bVal = parseFloat(b.cells[3].textContent.replace(/[^\d.-]/g, ''));
                break;
            default:
                return 0;
        }

        if (aVal < bVal) return currentSort.direction === 'asc' ? -1 : 1;
        if (aVal > bVal) return currentSort.direction === 'asc' ? 1 : -1;
        return 0;
    });

    // Re-append rows in sorted order
    rows.forEach(row => table.appendChild(row));
}

function toggleSelectAll() {
    const selectAll = document.getElementById('select-all');
    const checkboxes = document.querySelectorAll('.transaction-checkbox');

    checkboxes.forEach(cb => {
        cb.checked = selectAll.checked;
        if (selectAll.checked) {
            selectedTransactions.add(parseInt(cb.value));
        }
    });

    if (!selectAll.checked) {
        selectedTransactions.clear();
    }

    updateBulkActionsBar();
}

function updateSelection() {
    selectedTransactions.clear();
    const checkboxes = document.querySelectorAll('.transaction-checkbox:checked');
    checkboxes.forEach(cb => {
        selectedTransactions.add(parseInt(cb.value));
    });

    // Update select all checkbox
    const allCheckboxes = document.querySelectorAll('.transaction-checkbox');
    const selectAll = document.getElementById('select-all');
    selectAll.checked = allCheckboxes.length > 0 &&
                        checkboxes.length === allCheckboxes.length;

    updateBulkActionsBar();
}

function updateBulkActionsBar() {
    const bulkActions = document.getElementById('bulk-actions');
    const selectedCount = document.getElementById('selected-count');

    if (selectedTransactions.size > 0) {
        bulkActions.classList.remove('d-none');
        selectedCount.textContent = selectedTransactions.size;
    } else {
        bulkActions.classList.add('d-none');
    }
}

function clearSelection() {
    selectedTransactions.clear();
    document.querySelectorAll('.transaction-checkbox').forEach(cb => {
        cb.checked = false;
    });
    document.getElementById('select-all').checked = false;
    updateBulkActionsBar();
}

async function categorizeTransaction(selectElement) {
    const transactionId = selectElement.dataset.transactionId;
    const categoryId = selectElement.value;

    try {
        const response = await fetch(`/transactions/${transactionId}/categorize`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ category_id: categoryId || null })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to categorize');
        }

        showToast('Transaction categorized', 'success');

    } catch (error) {
        showToast(error.message, 'error');
        // Revert selection
        selectElement.value = selectElement.dataset.previousValue || '';
    }

    // Store current value for potential revert
    selectElement.dataset.previousValue = selectElement.value;
}

// ==================== AUTO-CATEGORIZE ====================

async function autoCategorize() {
    const btn = document.getElementById('auto-cat-btn');
    const text = document.getElementById('auto-cat-text');
    const spinner = document.getElementById('auto-cat-spinner');

    // Show loading state
    btn.disabled = true;
    text.textContent = 'Processing...';
    spinner.classList.remove('d-none');

    try {
        const response = await fetch('/transactions/auto-categorize', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to auto-categorize');
        }

        if (data.categorized > 0) {
            showToast(`Auto-categorized ${data.categorized} transactions (${data.remaining} remaining)`, 'success');
            // Reload page to show updated categories
            setTimeout(() => location.reload(), 1000);
        } else {
            showToast('No transactions could be auto-categorized. Categorize some manually first.', 'info');
        }

    } catch (error) {
        showToast(error.message, 'error');
    } finally {
        // Reset button
        btn.disabled = false;
        text.textContent = 'Auto-Categorize';
        spinner.classList.add('d-none');
    }
}

// ==================== BULK CATEGORIZE ====================

async function bulkCategorize() {
    const categoryId = document.getElementById('bulk-category').value;

    if (!categoryId) {
        showToast('Please select a category', 'warning');
        return;
    }

    if (selectedTransactions.size === 0) {
        showToast('No transactions selected', 'warning');
        return;
    }

    try {
        const response = await fetch('/transactions/bulk-categorize', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                transaction_ids: Array.from(selectedTransactions),
                category_id: categoryId
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to categorize');
        }

        showToast(`${data.updated} transactions categorized`, 'success');

        // Update UI - set all selected dropdowns to new category
        selectedTransactions.forEach(id => {
            const select = document.querySelector(`select[data-transaction-id="${id}"]`);
            if (select) {
                select.value = categoryId;
            }
        });

        clearSelection();

    } catch (error) {
        showToast(error.message, 'error');
    }
}
