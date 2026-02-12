// Categories page functionality

async function addCategory() {
    const name = document.getElementById('category-name').value.trim();
    const color = document.getElementById('category-color').value;

    if (!name) {
        showToast('Please enter a category name', 'warning');
        return;
    }

    try {
        const response = await fetch('/categories/add', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ name, color })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to add category');
        }

        showToast('Category added', 'success');

        // Close modal and reload page
        bootstrap.Modal.getInstance(document.getElementById('addCategoryModal')).hide();
        location.reload();

    } catch (error) {
        showToast(error.message, 'error');
    }
}

function editCategory(id, name, color) {
    document.getElementById('edit-category-id').value = id;
    document.getElementById('edit-category-name').value = name;
    document.getElementById('edit-category-color').value = color;

    new bootstrap.Modal(document.getElementById('editCategoryModal')).show();
}

async function saveCategory() {
    const id = document.getElementById('edit-category-id').value;
    const name = document.getElementById('edit-category-name').value.trim();
    const color = document.getElementById('edit-category-color').value;

    if (!name) {
        showToast('Please enter a category name', 'warning');
        return;
    }

    try {
        const response = await fetch(`/categories/${id}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ name, color })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to update category');
        }

        showToast('Category updated', 'success');

        // Close modal and reload page
        bootstrap.Modal.getInstance(document.getElementById('editCategoryModal')).hide();
        location.reload();

    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function deleteCategory(id, name) {
    if (!confirm(`Are you sure you want to delete the category "${name}"?`)) {
        return;
    }

    try {
        const response = await fetch(`/categories/${id}`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to delete category');
        }

        showToast('Category deleted', 'success');
        location.reload();

    } catch (error) {
        showToast(error.message, 'error');
    }
}
