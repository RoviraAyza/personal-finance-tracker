// Transactions page functionality

let selectedTransactions = new Set();

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
