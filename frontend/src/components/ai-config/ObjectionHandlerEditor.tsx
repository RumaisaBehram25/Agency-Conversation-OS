import Button from '../ui/Button';

interface ObjectionHandlerEditorProps {
  handlers: Record<string, string>;
  onChange: (handlers: Record<string, string>) => void;
}

export default function ObjectionHandlerEditor({
  handlers,
  onChange,
}: ObjectionHandlerEditorProps) {
  const entries = Object.entries(handlers);

  function addHandler() {
    const key = `Question ${entries.length + 1}`;
    onChange({ ...handlers, [key]: '' });
  }

  function removeHandler(key: string) {
    const updated = { ...handlers };
    delete updated[key];
    onChange(updated);
  }

  function updateKey(oldKey: string, newKey: string) {
    if (newKey === oldKey) return;
    const updated: Record<string, string> = {};
    for (const [k, v] of Object.entries(handlers)) {
      if (k === oldKey) {
        updated[newKey] = v;
      } else {
        updated[k] = v;
      }
    }
    onChange(updated);
  }

  function updateValue(key: string, value: string) {
    onChange({ ...handlers, [key]: value });
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <label className="block text-sm font-medium text-gray-700">
          Objection Handlers
        </label>
        <Button variant="secondary" size="sm" type="button" onClick={addHandler}>
          <svg className="mr-1 h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          Add Pair
        </Button>
      </div>
      <p className="text-xs text-gray-500 mb-4">
        Define common objections and the AI's recommended response for each.
      </p>

      {entries.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 py-6 text-center text-sm text-gray-400">
          No objection handlers configured. Click "Add Pair" to start.
        </div>
      ) : (
        <div className="space-y-4">
          {entries.map(([key, value], idx) => (
            <div
              key={idx}
              className="rounded-lg border border-gray-200 bg-gray-50 p-4"
            >
              <div className="flex items-start gap-3">
                <div className="flex-1 space-y-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">
                      Objection / Question
                    </label>
                    <input
                      type="text"
                      value={key}
                      onChange={(e) => updateKey(key, e.target.value)}
                      className="input-field"
                      placeholder="e.g., 'Is this covered by insurance?'"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">
                      AI Response
                    </label>
                    <textarea
                      value={value}
                      onChange={(e) => updateValue(key, e.target.value)}
                      rows={2}
                      className="input-field"
                      placeholder="How the AI should respond to this objection..."
                    />
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => removeHandler(key)}
                  className="mt-6 rounded-lg p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-500 transition-colors"
                  title="Remove"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                  </svg>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
