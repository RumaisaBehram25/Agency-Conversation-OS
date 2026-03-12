import { formatCurrency, truncate } from '../../utils/formatters';
import Badge from '../ui/Badge';
import Button from '../ui/Button';
import type { Product } from '../../types';

interface ProductTableProps {
  products: Product[];
  onEdit: (product: Product) => void;
  onDelete: (product: Product) => void;
  onToggleActive: (product: Product) => void;
}

export default function ProductTable({
  products,
  onEdit,
  onDelete,
  onToggleActive,
}: ProductTableProps) {
  if (products.length === 0) {
    return (
      <div className="card py-12 text-center text-gray-400">
        No products yet. Add your first product to get started.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Product
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Description
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Price
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Conversion Value
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Status
            </th>
            <th className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200">
          {products.map((product) => (
            <tr key={product.id} className="hover:bg-gray-50">
              <td className="whitespace-nowrap px-6 py-4">
                <p className="text-sm font-medium text-gray-900">{product.name}</p>
              </td>
              <td className="px-6 py-4">
                <p className="max-w-xs text-sm text-gray-600">
                  {truncate(product.description || '', 80)}
                </p>
              </td>
              <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-900">
                {formatCurrency(product.price)}
              </td>
              <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-900">
                {formatCurrency(product.conversion_value)}
              </td>
              <td className="whitespace-nowrap px-6 py-4">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggleActive(product);
                  }}
                  className="focus:outline-none"
                >
                  {product.is_active ? (
                    <Badge color="green">Active</Badge>
                  ) : (
                    <Badge color="gray">Inactive</Badge>
                  )}
                </button>
              </td>
              <td className="whitespace-nowrap px-6 py-4 text-right">
                <div className="flex justify-end gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onEdit(product)}
                  >
                    Edit
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onDelete(product)}
                    className="text-red-600 hover:text-red-700 hover:bg-red-50"
                  >
                    Delete
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
