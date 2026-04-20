import { useEffect, useState, useCallback } from 'react';
import {
  getCampaigns,
  createCampaign,
  updateCampaign,
  deleteCampaign,
  generateUTMs,
} from '../api/campaigns';
import type { AdCampaign, CampaignCreate, CampaignUTM } from '../types';
import Modal from '../components/ui/Modal';
import Button from '../components/ui/Button';
import LoadingSpinner from '../components/ui/LoadingSpinner';

// ── Copy-to-clipboard helper ─────────────────────────────────
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  function copy() {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }
  return (
    <button
      onClick={copy}
      title="Copy URL"
      className="ml-2 shrink-0 rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
    >
      {copied ? (
        <svg className="h-4 w-4 text-green-500" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
        </svg>
      ) : (
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184" />
        </svg>
      )}
    </button>
  );
}

// ── UTM URL row ──────────────────────────────────────────────
function UTMRow({ label, url }: { label: string; url: string | null }) {
  if (!url) return null;
  return (
    <div className="flex items-start gap-2 py-2 border-b border-gray-100 last:border-0">
      <span className="w-28 shrink-0 text-xs font-medium text-gray-500 pt-0.5">{label}</span>
      <span className="flex-1 break-all font-mono text-xs text-gray-700">{url}</span>
      <CopyButton text={url} />
    </div>
  );
}

// ── UTM panel inside campaign card ───────────────────────────
function UTMPanel({ utm }: { utm: CampaignUTM }) {
  return (
    <div className="mt-3 rounded-lg border border-blue-100 bg-blue-50 px-4 py-3">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-blue-600">UTM Tracking URLs</p>
      <UTMRow label="Product page" url={utm.product_page_utm_url} />
      <UTMRow label="Checkout" url={utm.checkout_utm_url} />
      <UTMRow label="Success page" url={utm.success_utm_url} />
      <p className="mt-2 text-[11px] text-gray-400">
        utm_source=<b>{utm.utm_source}</b> · utm_medium=<b>{utm.utm_medium}</b> · utm_campaign=<b>{utm.utm_campaign}</b>
      </p>
    </div>
  );
}

// ── Main page ────────────────────────────────────────────────
export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<AdCampaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');

  // Campaign form modal
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<AdCampaign | null>(null);
  const [formLoading, setFormLoading] = useState(false);
  const [formData, setFormData] = useState<CampaignCreate>({
    name: '',
    description: '',
    meta_campaign_id: '',
    is_attora_managed: true,
    is_active: true,
  });

  // Delete modal
  const [showDelete, setShowDelete] = useState(false);
  const [deleting, setDeleting] = useState<AdCampaign | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  // UTM modal
  const [showUTM, setShowUTM] = useState(false);
  const [utmTarget, setUtmTarget] = useState<AdCampaign | null>(null);
  const [utmLoading, setUtmLoading] = useState(false);
  const [utmData, setUtmData] = useState({ product_page_url: '', checkout_url: '', success_url: '' });
  const [utmError, setUtmError] = useState('');

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(''), 3000);
  }

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setCampaigns(await getCampaigns());
    } catch {
      setError('Failed to load campaigns');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  function openCreate() {
    setEditing(null);
    setFormData({ name: '', description: '', meta_campaign_id: '', is_attora_managed: true, is_active: true });
    setShowForm(true);
  }

  function openEdit(c: AdCampaign) {
    setEditing(c);
    setFormData({
      name: c.name,
      description: c.description ?? '',
      meta_campaign_id: c.meta_campaign_id ?? '',
      is_attora_managed: c.is_attora_managed,
      is_active: c.is_active,
    });
    setShowForm(true);
  }

  async function handleFormSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormLoading(true);
    try {
      const payload = {
        ...formData,
        description: formData.description || undefined,
        meta_campaign_id: formData.meta_campaign_id || undefined,
      };
      if (editing) {
        await updateCampaign(editing.id, payload);
        showToast('Campaign updated');
      } else {
        await createCampaign(payload);
        showToast('Campaign created');
      }
      setShowForm(false);
      load();
    } catch {
      setError('Failed to save campaign');
    } finally {
      setFormLoading(false);
    }
  }

  async function handleDelete() {
    if (!deleting) return;
    setDeleteLoading(true);
    try {
      await deleteCampaign(deleting.id);
      setShowDelete(false);
      setDeleting(null);
      showToast('Campaign deleted');
      load();
    } catch {
      setError('Failed to delete campaign');
    } finally {
      setDeleteLoading(false);
    }
  }

  function openUTM(c: AdCampaign) {
    setUtmTarget(c);
    setUtmData({
      product_page_url: c.utm?.product_page_url ?? '',
      checkout_url: c.utm?.checkout_url ?? '',
      success_url: c.utm?.success_url ?? '',
    });
    setUtmError('');
    setShowUTM(true);
  }

  async function handleGenerateUTMs(e: React.FormEvent) {
    e.preventDefault();
    if (!utmTarget) return;
    if (!utmData.product_page_url && !utmData.checkout_url && !utmData.success_url) {
      setUtmError('Enter at least one page URL');
      return;
    }
    setUtmLoading(true);
    setUtmError('');
    try {
      await generateUTMs(utmTarget.id, {
        product_page_url: utmData.product_page_url || undefined,
        checkout_url: utmData.checkout_url || undefined,
        success_url: utmData.success_url || undefined,
      });
      showToast('UTM URLs generated');
      setShowUTM(false);
      load();
    } catch {
      setUtmError('Failed to generate UTMs');
    } finally {
      setUtmLoading(false);
    }
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Campaigns</h1>
          <p className="mt-1 text-sm text-gray-500">
            Manage Attora-tracked ad campaigns and generate UTM tracking URLs
          </p>
        </div>
        <Button onClick={openCreate}>
          <svg className="mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          New Campaign
        </Button>
      </div>

      {toast && (
        <div className="mb-4 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
          {toast}
        </div>
      )}
      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <LoadingSpinner className="mt-12" />
      ) : campaigns.length === 0 ? (
        <div className="rounded-xl border-2 border-dashed border-gray-200 py-16 text-center">
          <svg className="mx-auto mb-3 h-10 w-10 text-gray-300" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.34 15.84c-.688-.06-1.386-.09-2.09-.09H7.5a4.5 4.5 0 110-9h.75c.704 0 1.402-.03 2.09-.09m0 9.18c.253.962.584 1.892.985 2.783.247.55.06 1.21-.463 1.511l-.657.38c-.551.318-1.26.117-1.527-.461a20.845 20.845 0 01-1.44-4.282m3.102.069a18.03 18.03 0 01-.59-4.59c0-1.586.205-3.124.59-4.59m0 9.18a23.848 23.848 0 018.835 2.535M10.34 6.66a23.847 23.847 0 008.835-2.535m0 0A23.74 23.74 0 0018.795 3m.38 1.125a23.91 23.91 0 011.014 5.395m-1.014 8.855c-.118.38-.245.754-.38 1.125m.38-1.125a23.91 23.91 0 001.014-5.395m0-3.46c.495.413.811 1.035.811 1.73 0 .695-.316 1.317-.811 1.73m0-3.46a24.347 24.347 0 010 3.46" />
          </svg>
          <p className="text-sm font-medium text-gray-500">No campaigns yet</p>
          <p className="mt-1 text-xs text-gray-400">Create a campaign to start generating UTM tracking URLs</p>
          <Button className="mt-4" onClick={openCreate}>Create your first campaign</Button>
        </div>
      ) : (
        <div className="space-y-4">
          {campaigns.map((c) => (
            <div key={c.id} className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              {/* Campaign header row */}
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-base font-semibold text-gray-900">{c.name}</h3>
                    {c.is_attora_managed && (
                      <span className="rounded-full bg-primary-100 px-2 py-0.5 text-[11px] font-medium text-primary-700">
                        Attora managed
                      </span>
                    )}
                    <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                      c.is_active
                        ? 'bg-green-100 text-green-700'
                        : 'bg-gray-100 text-gray-500'
                    }`}>
                      {c.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </div>
                  {c.description && (
                    <p className="mt-1 text-sm text-gray-500">{c.description}</p>
                  )}
                  {c.meta_campaign_id && (
                    <p className="mt-1 text-xs text-gray-400">
                      Meta campaign ID: <span className="font-mono">{c.meta_campaign_id}</span>
                    </p>
                  )}
                </div>

                {/* Action buttons */}
                <div className="flex shrink-0 items-center gap-2">
                  <Button
                    variant="secondary"
                    onClick={() => openUTM(c)}
                  >
                    <svg className="mr-1.5 h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" />
                    </svg>
                    {c.utm ? 'Edit UTMs' : 'Generate UTMs'}
                  </Button>
                  <button
                    onClick={() => openEdit(c)}
                    className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
                    title="Edit campaign"
                  >
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
                    </svg>
                  </button>
                  <button
                    onClick={() => { setDeleting(c); setShowDelete(true); }}
                    className="rounded-lg p-2 text-gray-400 hover:bg-red-50 hover:text-red-500 transition-colors"
                    title="Delete campaign"
                  >
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                    </svg>
                  </button>
                </div>
              </div>

              {/* UTM panel — shown if UTMs exist */}
              {c.utm && <UTMPanel utm={c.utm} />}
            </div>
          ))}
        </div>
      )}

      {/* ── Campaign Create/Edit Modal ── */}
      <Modal
        isOpen={showForm}
        onClose={() => setShowForm(false)}
        title={editing ? 'Edit Campaign' : 'New Campaign'}
      >
        <form onSubmit={handleFormSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Campaign name *</label>
            <input
              required
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
              value={formData.name}
              onChange={(e) => setFormData((d) => ({ ...d, name: e.target.value }))}
              placeholder="e.g. Summer Sale Instagram"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea
              rows={2}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
              value={formData.description ?? ''}
              onChange={(e) => setFormData((d) => ({ ...d, description: e.target.value }))}
              placeholder="Optional description"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Meta campaign ID</label>
            <input
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
              value={formData.meta_campaign_id ?? ''}
              onChange={(e) => setFormData((d) => ({ ...d, meta_campaign_id: e.target.value }))}
              placeholder="From Meta Ads Manager (optional)"
            />
          </div>
          <div className="flex items-center gap-6">
            <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
              <input
                type="checkbox"
                checked={formData.is_attora_managed}
                onChange={(e) => setFormData((d) => ({ ...d, is_attora_managed: e.target.checked }))}
                className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
              />
              Attora managed
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
              <input
                type="checkbox"
                checked={formData.is_active}
                onChange={(e) => setFormData((d) => ({ ...d, is_active: e.target.checked }))}
                className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
              />
              Active
            </label>
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <Button variant="secondary" type="button" onClick={() => setShowForm(false)}>Cancel</Button>
            <Button type="submit" loading={formLoading}>{editing ? 'Save changes' : 'Create campaign'}</Button>
          </div>
        </form>
      </Modal>

      {/* ── UTM Generate Modal ── */}
      <Modal
        isOpen={showUTM}
        onClose={() => setShowUTM(false)}
        title={`Generate UTM URLs — ${utmTarget?.name ?? ''}`}
        size="lg"
      >
        <form onSubmit={handleGenerateUTMs} className="space-y-4">
          <p className="text-sm text-gray-500">
            Enter the base URLs for each funnel stage. Attora will append UTM parameters so
            you can track visitors that came from Attora conversations.
          </p>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Product page URL
            </label>
            <input
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
              value={utmData.product_page_url}
              onChange={(e) => setUtmData((d) => ({ ...d, product_page_url: e.target.value }))}
              placeholder="https://yourstore.com/product/name"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Checkout page URL
            </label>
            <input
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
              value={utmData.checkout_url}
              onChange={(e) => setUtmData((d) => ({ ...d, checkout_url: e.target.value }))}
              placeholder="https://yourstore.com/checkout"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Purchase success page URL
            </label>
            <input
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
              value={utmData.success_url}
              onChange={(e) => setUtmData((d) => ({ ...d, success_url: e.target.value }))}
              placeholder="https://yourstore.com/thank-you"
            />
          </div>

          {utmError && (
            <p className="text-sm text-red-600">{utmError}</p>
          )}

          {/* Preview of what will be generated */}
          {(utmData.product_page_url || utmData.checkout_url || utmData.success_url) && (
            <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
              <p className="mb-1 text-xs font-medium text-gray-500">UTM parameters that will be added:</p>
              <p className="font-mono text-xs text-gray-600">
                ?utm_source=attora&utm_medium=messaging&utm_campaign={utmTarget ? utmTarget.name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '') : '...'}&utm_content=[stage]
              </p>
            </div>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <Button variant="secondary" type="button" onClick={() => setShowUTM(false)}>Cancel</Button>
            <Button type="submit" loading={utmLoading}>
              {utmTarget?.utm ? 'Regenerate UTMs' : 'Generate UTMs'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* ── Delete Confirmation Modal ── */}
      <Modal
        isOpen={showDelete}
        onClose={() => { setShowDelete(false); setDeleting(null); }}
        title="Delete Campaign"
        size="sm"
      >
        <p className="mb-6 text-sm text-gray-600">
          Are you sure you want to delete{' '}
          <span className="font-semibold text-gray-900">{deleting?.name}</span>?
          Any generated UTM URLs will be lost.
        </p>
        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={() => { setShowDelete(false); setDeleting(null); }}>Cancel</Button>
          <Button variant="danger" loading={deleteLoading} onClick={handleDelete}>Delete</Button>
        </div>
      </Modal>
    </div>
  );
}
