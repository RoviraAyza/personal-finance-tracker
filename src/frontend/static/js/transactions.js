// Transactions page functionality

let currentSort = { column: 'date', direction: 'desc' };

// ==================== SORTING ====================

function sortTable(column) {
    const table = document.querySelector('.table tbody');
    const rows = Array.from(table.querySelectorAll('tr[data-id]'));

    if (rows.length === 0) return;

    if (currentSort.column === column) {
        currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
    } else {
        currentSort.column = column;
        currentSort.direction = 'asc';
    }

    document.querySelectorAll('.sortable').forEach(th => {
        const icon = th.querySelector('.sort-icon');
        if (th.dataset.sort === column) {
            icon.textContent = currentSort.direction === 'asc' ? '\u2191' : '\u2193';
            th.classList.add('sorted');
        } else {
            icon.textContent = '\u2195';
            th.classList.remove('sorted');
        }
    });

    const headerRow = document.querySelector('.table thead tr');
    const headers = Array.from(headerRow.cells);
    const colIdx = headers.findIndex(th => th.dataset.sort === column);
    if (colIdx === -1) return;

    rows.sort((a, b) => {
        let aVal, bVal;
        switch (column) {
            case 'date':
                const aDateStr = a.cells[colIdx].textContent.trim();
                const bDateStr = b.cells[colIdx].textContent.trim();
                if (!aDateStr) return 1;
                if (!bDateStr) return -1;
                aVal = new Date(aDateStr.split('/').reverse().join('-'));
                bVal = new Date(bDateStr.split('/').reverse().join('-'));
                break;
            case 'description':
                aVal = a.cells[colIdx].textContent.toLowerCase();
                bVal = b.cells[colIdx].textContent.toLowerCase();
                break;
            case 'amount':
            case 'balance':
                const aText = a.cells[colIdx].textContent.replace(/[^\d.-]/g, '');
                const bText = b.cells[colIdx].textContent.replace(/[^\d.-]/g, '');
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

    rows.forEach(row => table.appendChild(row));
}

// ==================== TRANSACTION DETAIL MODAL ====================

let currentDetailId = null;

async function showTransactionDetail(id, event) {
    if (event && event.target) {
        const tag = event.target.tagName.toLowerCase();
        if (tag === 'input') return;
    }

    currentDetailId = id;
    const modal = new bootstrap.Modal(document.getElementById('transactionDetailModal'));
    const body = document.getElementById('transaction-detail-body');

    body.innerHTML = '<div class="text-center py-4"><div class="spinner-border" role="status"></div></div>';
    modal.show();

    try {
        const response = await fetch(`/api/transactions/${id}`);
        if (!response.ok) throw new Error('Failed to load transaction');
        const txn = await response.json();
        body.innerHTML = buildDetailHTML(txn);
        initDetailCategoryPicker(txn);
    } catch (error) {
        body.innerHTML = `<div class="alert alert-danger">${error.message}</div>`;
    }
}

function buildDetailHTML(txn) {
    const formatAmount = (val) => {
        if (val === null || val === undefined) return '';
        const cls = val < 0 ? 'text-danger' : 'text-success';
        return `<span class="${cls}"><strong>${parseFloat(val).toFixed(2)} EUR</strong></span>`;
    };

    const row = (label, value) => {
        if (value === null || value === undefined || value === '') return '';
        return `<tr><td class="text-muted" style="width:40%"><strong>${label}</strong></td><td>${value}</td></tr>`;
    };

    const section = (title, rows) => {
        const filtered = rows.filter(r => r !== '');
        if (filtered.length === 0) return '';
        return `
            <h6 class="mt-3 mb-2 text-primary">${title}</h6>
            <table class="table table-sm table-borderless mb-0">
                <tbody>${filtered.join('')}</tbody>
            </table>`;
    };

    // Category picker row — rendered inline in the main info section
    const categoryRow = `<tr>
        <td class="text-muted" style="width:40%"><strong>Categor\u00eda</strong></td>
        <td><div id="detail-category-picker"></div></td>
    </tr>`;

    const mainInfo = `
        <h6 class="mt-3 mb-2 text-primary">Informaci\u00f3n Principal</h6>
        <table class="table table-sm table-borderless mb-0">
            <tbody>
                ${row('Fecha Operaci\u00f3n', txn.date)}
                ${row('Fecha Valor', txn.value_date)}
                ${row('Descripci\u00f3n', txn.description)}
                ${row('Importe', formatAmount(txn.amount))}
                ${row('Saldo', txn.balance !== null ? `${parseFloat(txn.balance).toFixed(2)} EUR` : null)}
                ${categoryRow}
            </tbody>
        </table>`;

    const accountInfo = section('Datos de Cuenta', [
        row('N\u00famero de cuenta', txn.account_number),
        row('Oficina', txn.office),
        row('Divisa', txn.currency),
    ]);

    const conceptInfo = section('Conceptos y Referencias', [
        row('Concepto com\u00fan', txn.common_concept),
        row('Concepto propio', txn.bank_concept),
        row('Referencia 1', txn.reference_1),
        row('Referencia 2', txn.reference_2),
    ]);

    const complLabels = [
        'Comercio / Nombre', 'Detalle 2', 'Detalle 3', 'Detalle 4', 'Detalle 5',
        'Detalle 6', 'Detalle 7', 'Detalle 8', 'Detalle 9', 'Detalle 10',
    ];
    const complRows = [];
    for (let i = 1; i <= 10; i++) {
        const val = txn[`compl_${i}`];
        if (val) complRows.push(row(complLabels[i - 1], val));
    }
    const complInfo = section('Detalles Complementarios', complRows);

    const extraInfo = section('Otros', [
        row('Detalles extra', txn.extra_details),
    ]);

    return mainInfo + accountInfo + conceptInfo + complInfo + extraInfo;
}

async function initDetailCategoryPicker(txn) {
    const container = document.getElementById('detail-category-picker');
    if (!container) return;

    // Fetch categories
    let categories = [];
    try {
        const resp = await fetch('/api/categories');
        categories = await resp.json();
    } catch (e) {
        container.innerHTML = '<span class="text-muted">Error loading categories</span>';
        return;
    }

    // Build the picker: current badge + dropdown of options
    const currentCatId = txn.category_id;

    const badgeHTML = (catId, catColor, catName) => {
        if (catId) {
            return `<span class="badge" style="background-color:${catColor};cursor:pointer;" id="detail-cat-badge">${catName}</span>`;
        }
        return `<span class="badge bg-light text-muted border" style="cursor:pointer;" id="detail-cat-badge">Sin categor\u00eda</span>`;
    };

    let optionsHTML = `<div class="detail-cat-option" data-id="" data-color="" data-name="">
        <span class="category-dot" style="background-color:#ccc;"></span> Sin categor\u00eda
    </div>`;
    for (const cat of categories) {
        const active = cat.id === currentCatId ? ' detail-cat-active' : '';
        optionsHTML += `<div class="detail-cat-option${active}" data-id="${cat.id}" data-color="${cat.color}" data-name="${cat.name}">
            <span class="category-dot" style="background-color:${cat.color};"></span> ${cat.name}
        </div>`;
    }

    container.innerHTML = `
        <div class="detail-cat-wrapper">
            ${badgeHTML(currentCatId, txn.category_color, txn.category_name)}
            <div class="detail-cat-dropdown">${optionsHTML}</div>
        </div>`;

    // Toggle dropdown on badge click
    const badge = container.querySelector('#detail-cat-badge');
    const dropdown = container.querySelector('.detail-cat-dropdown');

    badge.addEventListener('click', () => {
        dropdown.classList.toggle('show');
    });

    // Handle option click
    container.querySelectorAll('.detail-cat-option').forEach(opt => {
        opt.addEventListener('click', async () => {
            const catId = opt.dataset.id;
            const catColor = opt.dataset.color;
            const catName = opt.dataset.name;

            dropdown.classList.remove('show');

            // Update badge immediately
            if (catId) {
                badge.textContent = catName;
                badge.style.backgroundColor = catColor;
                badge.className = 'badge';
                badge.style.cursor = 'pointer';
            } else {
                badge.textContent = 'Sin categor\u00eda';
                badge.style.backgroundColor = '';
                badge.className = 'badge bg-light text-muted border';
                badge.style.cursor = 'pointer';
            }

            // Mark active
            container.querySelectorAll('.detail-cat-option').forEach(o => o.classList.remove('detail-cat-active'));
            opt.classList.add('detail-cat-active');

            // Save to server
            try {
                const response = await fetch(`/transactions/${currentDetailId}/categorize`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ category_id: catId || null })
                });
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || 'Failed');

                // Update the dot in the table row
                updateRowDot(currentDetailId, catColor);

                // Update sibling dots too
                if (data.also_categorized && data.also_categorized.length > 0) {
                    for (const sib of data.also_categorized) {
                        updateRowDot(sib.id, catColor);
                    }
                    showToast(`Categorized (+${data.also_categorized.length} with same description)`, 'success');
                } else {
                    showToast('Category updated', 'success');
                }
            } catch (error) {
                showToast(error.message, 'error');
            }
        });
    });
}

function updateRowDot(transactionId, color) {
    const row = document.querySelector(`tr[data-id="${transactionId}"]`);
    if (!row) return;
    const dot = row.querySelector('.cat-dot');
    if (dot) {
        dot.style.backgroundColor = color || 'transparent';
    }
}

// ==================== FILTER BAR ====================

function getUrlParams() {
    const params = new URLSearchParams(window.location.search);
    const result = {};
    for (const [key, value] of params.entries()) {
        if (result[key]) {
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

function removeFilter(filterName) {
    const params = getUrlParams();
    delete params[filterName];
    window.location.href = buildUrl(params);
}

function removeCategoryFilter(categoryId) {
    const params = getUrlParams();
    if (params.category) {
        if (Array.isArray(params.category)) {
            params.category = params.category.filter(id => id !== categoryId);
            if (params.category.length === 0) delete params.category;
        } else if (params.category === categoryId) {
            delete params.category;
        }
    }
    window.location.href = buildUrl(params);
}

function clearAllFilters() {
    window.location.href = '/transactions';
}

function updateFilterUI() {
    const params = getUrlParams();
    const filterKeys = Object.keys(params).filter(key => params[key] !== '');
    const hasFilters = filterKeys.length > 0;

    const clearBtn = document.getElementById('clear-filters-btn');
    if (clearBtn) {
        clearBtn.style.display = hasFilters ? 'inline-block' : 'none';
    }

    const filterCount = document.getElementById('filter-count');
    if (filterCount) {
        filterCount.textContent = hasFilters ? `(${filterKeys.length} active)` : '';
    }
}

function initFilterToggle() {
    const filterFields = document.getElementById('filterFields');
    const toggleIcon = document.querySelector('.filter-toggle-icon');

    if (filterFields && toggleIcon) {
        filterFields.addEventListener('show.bs.collapse', () => {
            toggleIcon.innerHTML = '&#9660;';
        });
        filterFields.addEventListener('hide.bs.collapse', () => {
            toggleIcon.innerHTML = '&#9654;';
        });
    }
}

function updateCategoryLabel() {
    const checkboxes = document.querySelectorAll('.category-dropdown-menu input[type="checkbox"]');
    const checked = document.querySelectorAll('.category-dropdown-menu input[type="checkbox"]:checked');
    const label = document.getElementById('categoryDropdownLabel');

    if (label) {
        if (checked.length === 0 || checked.length === checkboxes.length) {
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
    account: false
};

function getColumnVisibility() {
    try {
        const saved = localStorage.getItem(COLUMN_VISIBILITY_KEY);
        if (saved) {
            const parsed = JSON.parse(saved);
            delete parsed.category;
            return { ...DEFAULT_VISIBILITY, ...parsed };
        }
    } catch (e) {}
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
        const checkbox = document.querySelector(`[data-toggle-col="${col}"]`);
        if (checkbox) checkbox.checked = visible;
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

    document.querySelectorAll('[data-toggle-col]').forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            toggleColumn(this.dataset.toggleCol);
        });
    });
}

// ==================== INIT ====================

document.addEventListener('DOMContentLoaded', function() {
    updateFilterUI();
    initFilterToggle();
    updateCategoryLabel();
    initColumnToggle();
});
