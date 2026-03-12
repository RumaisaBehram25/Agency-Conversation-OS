import { useState, useEffect } from 'react';
import Button from '../ui/Button';
import ObjectionHandlerEditor from './ObjectionHandlerEditor';
import type { AIConfig, AIConfigUpdate } from '../../types';

interface AIConfigEditorProps {
  config: AIConfig;
  onSave: (data: AIConfigUpdate) => Promise<void>;
}

interface ConfigSection {
  key: keyof AIConfigUpdate;
  label: string;
  description: string;
  rows: number;
}

const sections: ConfigSection[] = [
  {
    key: 'brand_voice',
    label: 'Brand Voice',
    description:
      'Define the tone and personality of AI responses. E.g., professional, friendly, empathetic.',
    rows: 4,
  },
  {
    key: 'product_knowledge',
    label: 'Product Knowledge',
    description:
      'Information about your products/services the AI should know when answering questions.',
    rows: 6,
  },
  {
    key: 'compliance_rules',
    label: 'Compliance Rules',
    description:
      'Rules the AI must follow. E.g., no medical claims, no price guarantees, always recommend consulting a provider.',
    rows: 5,
  },
  {
    key: 'greeting_message',
    label: 'Greeting Message',
    description: 'The initial message when a new conversation starts.',
    rows: 3,
  },
  {
    key: 'conversion_playbook',
    label: 'Conversion Playbook',
    description:
      'Strategy and scripts the AI should follow to guide users toward conversion.',
    rows: 6,
  },
  {
    key: 'fallback_message',
    label: 'Fallback Message',
    description:
      'Message sent when the AI cannot generate a confident response.',
    rows: 3,
  },
];

export default function AIConfigEditor({ config, onSave }: AIConfigEditorProps) {
  const [form, setForm] = useState<AIConfigUpdate>({
    brand_voice: '',
    product_knowledge: '',
    compliance_rules: '',
    greeting_message: '',
    conversion_playbook: '',
    fallback_message: '',
    objection_handlers: {},
  });
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState('');

  useEffect(() => {
    setForm({
      brand_voice: config.brand_voice || '',
      product_knowledge: config.product_knowledge || '',
      compliance_rules: config.compliance_rules || '',
      greeting_message: config.greeting_message || '',
      conversion_playbook: config.conversion_playbook || '',
      fallback_message: config.fallback_message || '',
      objection_handlers: config.objection_handlers || {},
    });
  }, [config]);

  function updateField(key: keyof AIConfigUpdate, value: string | Record<string, string>) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      await onSave(form);
      setToast('AI configuration saved successfully');
      setTimeout(() => setToast(''), 3000);
    } catch {
      setToast('');
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

      <div className="space-y-8">
        {sections.map((section) => (
          <div key={section.key}>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {section.label}
            </label>
            <p className="text-xs text-gray-500 mb-2">{section.description}</p>
            <textarea
              value={(form[section.key] as string) || ''}
              onChange={(e) => updateField(section.key, e.target.value)}
              rows={section.rows}
              className="input-field font-mono text-sm"
              placeholder={`Enter ${section.label.toLowerCase()}...`}
            />
          </div>
        ))}

        {/* Objection Handlers */}
        <div className="border-t border-gray-200 pt-8">
          <ObjectionHandlerEditor
            handlers={(form.objection_handlers as Record<string, string>) || {}}
            onChange={(handlers) => updateField('objection_handlers', handlers)}
          />
        </div>
      </div>

      <div className="mt-8 flex justify-end border-t border-gray-200 pt-6">
        <Button type="submit" loading={loading} size="lg">
          Save Configuration
        </Button>
      </div>
    </form>
  );
}
