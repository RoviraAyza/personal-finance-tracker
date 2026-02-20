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

    // Find column index dynamically by scanning header cells for data-sort or data-col
    const headerRow = document.querySelector('.table thead tr');
    const headers = Array.from(headerRow.cells);
    let colIdx = -1;

    if (column === 'date') {
        // Date column is always the second visible cell (index 1, after checkbox)
        colIdx = headers.findIndex(th => th.dataset.sort === 'date');
    } else {
        colIdx = headers.findIndex(th => th.dataset.sort === column);
    }

    if (colIdx === -1) return;

    // Sort rows
    rows.sort((a, b) => {
        let aVal, bVal;
        const idx = colIdx;

        switch (column) {
            case 'date':
                const aDateStr = a.cells[idx].textContent.trim();
                const bDateStr = b.cells[idx].textContent.trim();
                if (!aDateStr) return 1;
                if (!bDateStr) return -1;
                aVal = new Date(aDateStr.split('/').reverse().join('-'));
                bVal = new Date(bDateStr.split('/').reverse().join('-'));
                break;
            case 'description':
                aVal = a.cells[idx].textContent.toLowerCase();
                bVal = b.cells[idx].textContent.toLowerCase();
                break;
            case 'amount':
            case 'balance':
                const aText = a.cells[idx].textContent.replace(/[^\d.-]/g, '');
                const bText = b.cells[idx].textContent.replace(/[^\d.-]/g, '');
                aVal = aText ? parseFloat(aText) : 0;
                bVal = bText ? parseFloat(bText) : 0;
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

// ==================== FILTER BAR ====================

/**
 * Get current URL parameters as an object
 */
function getUrlParams() {
    const params = new URLSearchParams(window.location.search);
    const result = {};
    for (const [key, value] of params.entries()) {
        if (result[key]) {
            // Handle multiple values (like category)
            if (Array.isArray(result[key])) {
                result[key].push(value);
            } else {
                result[key] = [result[key], value];
            }
        } else {
            result[key] = value;
        }
    }
    return result;
}

/**
 * Build URL with given parameters
 */
function buildUrl(params) {
    const url = new URL(window.location.pathname, window.location.origin);
    for (const [key, value] of Object.entries(params)) {
        if (Array.isArray(value)) {
            value.forEach(v => url.searchParams.append(key, v));
        } else if (value !== null && value !== undefined && value !== '') {
            url.searchParams.set(key, value);
        }
    }
    return url.toString();
}

/**
 * Remove a single filter and redirect
 */
function removeFilter(filterName) {
    const params = getUrlParams();
    delete params[filterName];
    window.location.href = buildUrl(params);
}

/**
 * Remove a category from the multi-select filter
 */
function removeCategoryFilter(categoryId) {
    const params = getUrlParams();

    if (params.category) {
        if (Array.isArray(params.category)) {
            params.category = params.category.filter(id => id !== categoryId);
            if (params.category.length === 0) {
                delete params.category;
            }
        } else if (params.category === categoryId) {
            delete params.category;
        }
    }

    window.location.href = buildUrl(params);
}

/**
 * Clear all filters and redirect to base transactions page
 */
function clearAllFilters() {
    window.location.href = '/transactions';
}

/**
 * Update UI elements based on active filters
 */
function updateFilterUI() {
    const params = getUrlParams();
    const filterKeys = Object.keys(params).filter(key => params[key] !== '');
    const hasFilters = filterKeys.length > 0;

    // Show/hide clear button
    const clearBtn = document.getElementById('clear-filters-btn');
    if (clearBtn) {
        clearBtn.style.display = hasFilters ? 'inline-block' : 'none';
    }

    // Update filter count badge
    const filterCount = document.getElementById('filter-count');
    if (filterCount) {
        filterCount.textContent = hasFilters ? `(${filterKeys.length} active)` : '';
    }
}

/**
 * Handle collapse toggle icon
 */
function initFilterToggle() {
    const filterFields = document.getElementById('filterFields');
    const toggleIcon = document.querySelector('.filter-toggle-icon');

    if (filterFields && toggleIcon) {
        filterFields.addEventListener('show.bs.collapse', () => {
            toggleIcon.innerHTML = '&#9660;'; // Down arrow
        });

        filterFields.addEventListener('hide.bs.collapse', () => {
            toggleIcon.innerHTML = '&#9654;'; // Right arrow
        });
    }
}

/**
 * Update category dropdown label based on selected checkboxes
 */
function updateCategoryLabel() {
    const checkboxes = document.querySelectorAll('.category-dropdown-menu input[type="checkbox"]');
    const checked = document.querySelectorAll('.category-dropdown-menu input[type="checkbox"]:checked');
    const label = document.getElementById('categoryDropdownLabel');

    if (label) {
        if (checked.length === 0) {
            label.textContent = 'All categories';
        } else if (checked.length === checkboxes.length) {
            label.textContent = 'All categories';
        } else {
            label.textContent = checked.length + ' selected';
        }
    }
}

// ==================== COLUMN VISIBILITY ====================

const COLUMN_VISIBILITY_KEY = 'columnVisibility';
const DEFAULT_VISIBILITY = {
    description: true,
    extra_details: false,
    amount: true,
    balance: false,
    account: false,
    category: true
};

function getColumnVisibility() {
    try {
        const saved = localStorage.getItem(COLUMN_VISIBILITY_KEY);
        if (saved) {
            return { ...DEFAULT_VISIBILITY, ...JSON.parse(saved) };
        }
    } catch (e) {
        // ignore parse errors
    }
    return { ...DEFAULT_VISIBILITY };
}

function saveColumnVisibility(visibility) {
    localStorage.setItem(COLUMN_VISIBILITY_KEY, JSON.stringify(visibility));
}

function applyColumnVisibility(visibility) {
    for (const [col, visible] of Object.entries(visibility)) {
        const cells = document.querySelectorAll(`[data-col="${col}"]`);
        cells.forEach(cell => {
            cell.classList.toggle('col-hidden', !visible);
        });

        // Sync the dropdown checkbox
        const checkbox = document.querySelector(`[data-toggle-col="${col}"]`);
        if (checkbox) {
            checkbox.checked = visible;
        }
    }
}

function toggleColumn(colName) {
    const visibility = getColumnVisibility();
    visibility[colName] = !visibility[colName];
    saveColumnVisibility(visibility);
    applyColumnVisibility(visibility);
}

function initColumnToggle() {
    const visibility = getColumnVisibility();
    applyColumnVisibility(visibility);

    // Bind change events on dropdown checkboxes
    document.querySelectorAll('[data-toggle-col]').forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            toggleColumn(this.dataset.toggleCol);
        });
    });
}

/**
 * Initialize filter bar on page load
 */
document.addEventListener('DOMContentLoaded', function() {
    updateFilterUI();
    initFilterToggle();
    updateCategoryLabel();
    initColumnToggle();
});
