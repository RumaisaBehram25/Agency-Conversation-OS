import { useEffect, useState, useCallback } from 'react';
import {
  getProducts,
  createProduct,
  updateProduct,
  deleteProduct,
} from '../api/products';
import type { Product, ProductCreate } from '../types';
import ProductTable from '../components/products/ProductTable';
import ProductForm from '../components/products/ProductForm';
import Modal from '../components/ui/Modal';
import Button from '../components/ui/Button';
import LoadingSpinner from '../components/ui/LoadingSpinner';

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Modal state
  const [showForm, setShowForm] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deletingProduct, setDeletingProduct] = useState<Product | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  // Toast
  const [toast, setToast] = useState('');

  function showToast(message: string) {
    setToast(message);
    setTimeout(() => setToast(''), 3000);
  }

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await getProducts();
      setProducts(result);
    } catch {
      setError('Failed to load products');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCreate(data: ProductCreate) {
    await createProduct(data);
    setShowForm(false);
    setEditingProduct(null);
    showToast('Product created successfully');
    load();
  }

  async function handleUpdate(data: ProductCreate) {
    if (!editingProduct) return;
    await updateProduct(editingProduct.id, data);
    setShowForm(false);
    setEditingProduct(null);
    showToast('Product updated successfully');
    load();
  }

  async function handleDelete() {
    if (!deletingProduct) return;
    setDeleteLoading(true);
    try {
      await deleteProduct(deletingProduct.id);
      setShowDeleteConfirm(false);
      setDeletingProduct(null);
      showToast('Product deleted successfully');
      load();
    } catch {
      setError('Failed to delete product');
    } finally {
      setDeleteLoading(false);
    }
  }

  async function handleToggleActive(product: Product) {
    try {
      await updateProduct(product.id, { is_active: !product.is_active });
      showToast(`Product ${product.is_active ? 'deactivated' : 'activated'}`);
      load();
    } catch {
      setError('Failed to update product');
    }
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Products</h1>
          <p className="mt-1 text-sm text-gray-500">
            Manage your product catalog for AI conversations
          </p>
        </div>
        <Button
          onClick={() => {
            setEditingProduct(null);
            setShowForm(true);
          }}
        >
          <svg className="mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          Add Product
        </Button>
      </div>

      {/* Toast */}
      {toast && (
        <div className="mb-4 rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-700">
          {toast}
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <LoadingSpinner className="mt-12" />
      ) : (
        <ProductTable
          products={products}
          onEdit={(product) => {
            setEditingProduct(product);
            setShowForm(true);
          }}
          onDelete={(product) => {
            setDeletingProduct(product);
            setShowDeleteConfirm(true);
          }}
          onToggleActive={handleToggleActive}
        />
      )}

      {/* Add/Edit Modal */}
      <Modal
        isOpen={showForm}
        onClose={() => {
          setShowForm(false);
          setEditingProduct(null);
        }}
        title={editingProduct ? 'Edit Product' : 'Add Product'}
      >
        <ProductForm
          product={editingProduct}
          onSubmit={editingProduct ? handleUpdate : handleCreate}
          onCancel={() => {
            setShowForm(false);
            setEditingProduct(null);
          }}
        />
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={showDeleteConfirm}
        onClose={() => {
          setShowDeleteConfirm(false);
          setDeletingProduct(null);
        }}
        title="Delete Product"
        size="sm"
      >
        <p className="text-sm text-gray-600 mb-6">
          Are you sure you want to delete{' '}
          <span className="font-semibold text-gray-900">{deletingProduct?.name}</span>?
          This action cannot be undone.
        </p>
        <div className="flex justify-end gap-3">
          <Button
            variant="secondary"
            onClick={() => {
              setShowDeleteConfirm(false);
              setDeletingProduct(null);
            }}
          >
            Cancel
          </Button>
          <Button variant="danger" loading={deleteLoading} onClick={handleDelete}>
            Delete Product
          </Button>
        </div>
      </Modal>
    </div>
  );
}
