import client from './client';
import type { Product, ProductCreate, ProductUpdate } from '../types';

export async function getProducts(): Promise<Product[]> {
  const response = await client.get<Product[]>('/products');
  return response.data;
}

export async function getProduct(id: string): Promise<Product> {
  const response = await client.get<Product>(`/products/${id}`);
  return response.data;
}

export async function createProduct(data: ProductCreate): Promise<Product> {
  const response = await client.post<Product>('/products', data);
  return response.data;
}

export async function updateProduct(id: string, data: ProductUpdate): Promise<Product> {
  const response = await client.put<Product>(`/products/${id}`, data);
  return response.data;
}

export async function deleteProduct(id: string): Promise<void> {
  await client.delete(`/products/${id}`);
}
