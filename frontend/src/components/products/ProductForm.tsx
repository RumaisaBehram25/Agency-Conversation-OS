import { useState, useEffect } from 'react';
import Button from '../ui/Button';
import Input from '../ui/Input';
import type { Product, ProductCreate } from '../../types';

interface ProductFormProps {
  product?: Product | null;
  onSubmit: (data: ProductCreate) => Promise<void>;
  onCancel: () => void;
}

export default function ProductForm({ product, onSubmit, onCancel }: ProductFormProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [price, setPrice] = useState('');
  const [conversionValue, setConversionValue] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (product) {
      setName(product.name);
      setDescription(product.description);
      setPrice(String(product.price));
      setConversionValue(String(product.conversion_value));
      setIsActive(product.is_active);
    }
  }, [product]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await onSubmit({
        name,
        description,
        price: parseFloat(price) || 0,
        conversion_value: parseFloat(conversionValue) || 0,
        is_active: isActive,
      });
    } catch {
      setError('Failed to save product');
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <Input
        label="Product Name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="e.g., Virtual Consultation"
        required
      />

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={3}
          className="input-field"
          placeholder="Brief description of the product or service..."
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Input
          label="Price ($)"
          type="number"
          step="0.01"
          min="0"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          placeholder="99.00"
          required
        />
        <Input
          label="Conversion Value ($)"
          type="number"
          step="0.01"
          min="0"
          value={conversionValue}
          onChange={(e) => setConversionValue(e.target.value)}
          placeholder="99.00"
          required
        />
      </div>

      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="is_active"
          checked={isActive}
          onChange={(e) => setIsActive(e.target.checked)}
          className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
        />
        <label htmlFor="is_active" className="text-sm text-gray-700">
          Active
        </label>
      </div>

      <div className="flex justify-end gap-3 pt-4 border-t border-gray-200">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" loading={loading}>
          {product ? 'Update Product' : 'Create Product'}
        </Button>
      </div>
    </form>
  );
}
