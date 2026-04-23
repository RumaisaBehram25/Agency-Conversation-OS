import { useState, useEffect } from 'react';
import Button from '../ui/Button';
import Input from '../ui/Input';
import type { SettingsResponse, SettingsUpdate } from '../../types';

interface SettingsFormProps {
  settings: SettingsResponse;
  onSave: (data: SettingsUpdate) => Promise<void>;
}

function isMasked(value: string | null | undefined): boolean {
  const safeValue = value || '';
  return /^\*+.{0,4}$/.test(safeValue) || safeValue === '';
}

export default function SettingsForm({ settings, onSave }: SettingsFormProps) {
  const [form, setForm] = useState<SettingsUpdate>({
    manychat_api_key: '',
    manychat_page_id: '',
    manychat_account_id: '',
    meta_pixel_id: '',
    meta_capi_token: '',
    meta_ad_account_id: '',
    meta_page_id: '',
    meta_business_manager_id: '',
    hyros_api_key: '',
  });
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    setForm({
      manychat_api_key: settings.manychat_api_key || '',
      manychat_page_id: settings.manychat_page_id || '',
      manychat_account_id: settings.manychat_account_id || '',
      meta_pixel_id: settings.meta_pixel_id || '',
      meta_capi_token: settings.meta_capi_token || '',
      meta_ad_account_id: settings.meta_ad_account_id || '',
      meta_page_id: settings.meta_page_id || '',
      meta_business_manager_id: settings.meta_business_manager_id || '',
      hyros_api_key: settings.hyros_api_key || '',
    });
  }, [settings]);

  function updateField(key: keyof SettingsUpdate, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      // Only send fields that were actually changed (not still masked)
      const update: SettingsUpdate = {};
      for (const [key, value] of Object.entries(form)) {
        if (value && !isMasked(value)) {
          (update as Record<string, string>)[key] = value;
        }
      }
      await onSave(update);
      setToast('Settings saved successfully');
      setTimeout(() => setToast(''), 3000);
    } catch {
      setError('Failed to save settings');
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      {toast && (
        <div className="mb-6 rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-700">
          {toast}
        </div>
      )}
      {error && (
        <div className="mb-6 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* ManyChat Section */}
      <div className="mb-8">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-100">
            <svg className="h-4 w-4 text-blue-600" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" />
            </svg>
          </div>
          <h3 className="text-base font-semibold text-gray-900">ManyChat</h3>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input
            label="API Key"
            type="password"
            value={form.manychat_api_key || ''}
            onChange={(e) => updateField('manychat_api_key', e.target.value)}
            placeholder={isMasked(settings.manychat_api_key) ? 'Enter new API key to update' : ''}
            helpText={isMasked(settings.manychat_api_key) ? 'Current key is masked. Enter a new value to update.' : ''}
            className="sm:col-span-2"
          />
          <Input
            label="Page ID"
            value={form.manychat_page_id || ''}
            onChange={(e) => updateField('manychat_page_id', e.target.value)}
            placeholder="ManyChat Page ID"
          />
          <Input
            label="Account ID"
            value={form.manychat_account_id || ''}
            onChange={(e) => updateField('manychat_account_id', e.target.value)}
            placeholder="ManyChat Account ID"
          />
        </div>
      </div>

      {/* Meta Section */}
      <div className="mb-8 border-t border-gray-200 pt-8">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-100">
            <svg className="h-4 w-4 text-indigo-600" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
            </svg>
          </div>
          <h3 className="text-base font-semibold text-gray-900">Meta (Facebook)</h3>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input
            label="Pixel ID"
            value={form.meta_pixel_id || ''}
            onChange={(e) => updateField('meta_pixel_id', e.target.value)}
            placeholder="Meta Pixel ID"
          />
          <Input
            label="CAPI Token"
            type="password"
            value={form.meta_capi_token || ''}
            onChange={(e) => updateField('meta_capi_token', e.target.value)}
            placeholder={isMasked(settings.meta_capi_token) ? 'Enter new token to update' : ''}
            helpText={isMasked(settings.meta_capi_token) ? 'Current token is masked. Enter a new value to update.' : ''}
          />
          <Input
            label="Ad Account ID"
            value={form.meta_ad_account_id || ''}
            onChange={(e) => updateField('meta_ad_account_id', e.target.value)}
            placeholder="act_123456789"
          />
          <Input
            label="Page ID"
            value={form.meta_page_id || ''}
            onChange={(e) => updateField('meta_page_id', e.target.value)}
            placeholder="Meta Page ID"
          />
          <Input
            label="Business Manager ID"
            value={form.meta_business_manager_id || ''}
            onChange={(e) => updateField('meta_business_manager_id', e.target.value)}
            placeholder="Business Manager ID"
            className="sm:col-span-2"
          />
        </div>
      </div>

      {/* Hyros Section */}
      <div className="mb-8 border-t border-gray-200 pt-8">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-100">
            <svg className="h-4 w-4 text-emerald-600" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12.75l5.159-5.159a2.25 2.25 0 013.182 0l1.409 1.409a2.25 2.25 0 003.182 0l3.909-3.909m0 0h-3.375m3.375 0v3.375M3.75 20.25h16.5" />
            </svg>
          </div>
          <h3 className="text-base font-semibold text-gray-900">Hyros</h3>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input
            label="API Key"
            type="password"
            value={form.hyros_api_key || ''}
            onChange={(e) => updateField('hyros_api_key', e.target.value)}
            placeholder={isMasked(settings.hyros_api_key) ? 'Enter new Hyros API key to update' : ''}
            helpText={isMasked(settings.hyros_api_key) ? 'Current key is masked. Enter a new value to update.' : ''}
            className="sm:col-span-2"
          />
        </div>
      </div>

      <div className="flex justify-end border-t border-gray-200 pt-6">
        <Button type="submit" loading={loading} size="lg">
          Save Settings
        </Button>
      </div>
    </form>
  );
}
