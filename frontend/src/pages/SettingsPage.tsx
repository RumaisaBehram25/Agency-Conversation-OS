import { useEffect, useState } from 'react';
import { getSettings, updateSettings } from '../api/settings';
import type { SettingsResponse, SettingsUpdate } from '../types';
import SettingsForm from '../components/settings/SettingsForm';
import LoadingSpinner from '../components/ui/LoadingSpinner';

export default function SettingsPage() {
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    async function load() {
      try {
        const result = await getSettings();
        setSettings(result);
      } catch {
        setError('Failed to load settings');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  async function handleSave(data: SettingsUpdate) {
    const result = await updateSettings(data);
    setSettings(result);
  }

  if (loading) {
    return <LoadingSpinner className="mt-20" size="lg" />;
  }

  if (error) {
    return (
      <div className="mt-20 text-center text-red-600">{error}</div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <p className="mt-1 text-sm text-gray-500">
          Configure your ManyChat and Meta integration credentials
        </p>
      </div>

      <div className="card">
        {settings && <SettingsForm settings={settings} onSave={handleSave} />}
      </div>
    </div>
  );
}
