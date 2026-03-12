import client from './client';
import type { AuthTokens, UserProfile } from '../types';

export async function login(email: string, password: string): Promise<AuthTokens> {
  const response = await client.post<AuthTokens>('/auth/login', { email, password });
  return response.data;
}

export async function register(
  email: string,
  password: string,
  full_name: string,
  org_name: string
): Promise<AuthTokens> {
  const response = await client.post<AuthTokens>('/auth/register', {
    email,
    password,
    full_name,
    org_name,
  });
  return response.data;
}

export async function refreshToken(refresh_token: string): Promise<AuthTokens> {
  const response = await client.post<AuthTokens>('/auth/refresh', { refresh_token });
  return response.data;
}

export async function getMe(): Promise<UserProfile> {
  const response = await client.get<UserProfile>('/auth/me');
  return response.data;
}
