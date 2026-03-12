import { useEffect, useState } from 'react';
import { getAIConfig, updateAIConfig } from '../api/aiConfig';
import type { AIConfig, AIConfigUpdate } from '../types';
import AIConfigEditor from '../components/ai-config/AIConfigEditor';
import LoadingSpinner from '../components/ui/LoadingSpinner';

export default function AIConfigPage() {
  const [config, setConfig] = useState<AIConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    async function load() {
      try {
        const result = await getAIConfig();
        setConfig(result);
      } catch {
        setError('Failed to load AI configuration');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  async function handleSave(data: AIConfigUpdate) {
    const result = await updateAIConfig(data);
    setConfig(result);
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
        <h1 className="text-2xl font-bold text-gray-900">AI Configuration</h1>
        <p className="mt-1 text-sm text-gray-500">
          Configure your AI conversation engine's behavior, knowledge, and compliance rules
        </p>
      </div>

      <div className="card">
        {config && <AIConfigEditor config={config} onSave={handleSave} />}
      </div>
    </div>
  );
}
