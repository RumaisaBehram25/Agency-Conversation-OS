import { useCallback, useEffect, useState } from 'react';
import {
  createAdCampaign,
  deleteAdCampaign,
  generateCampaignUtms,
  listAdCampaigns,
} from '../api/campaigns';
import type { AdCampaign } from '../types';
import LoadingSpinner from '../components/ui/LoadingSpinner';

interface NewCampaignForm {
  name: string;
  description: string;
  meta_campaign_id: string;
  meta_ad_set_id: string;
}

interface UtmForm {
  product_page_url: string;
  checkout_url: string;
  success_url: string;
}

const EMPTY_NEW: NewCampaignForm = {
  name: '',
  description: '',
  meta_campaign_id: '',
  meta_ad_set_id: '',
};

const EMPTY_UTM: UtmForm = {
  product_page_url: '',
  checkout_url: '',
  success_url: '',
};

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<AdCampaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [newCampaign, setNewCampaign] = useState<NewCampaignForm>(EMPTY_NEW);
  const [creating, setCreating] = useState(false);

  const [utmTarget, setUtmTarget] = useState<string | null>(null);
  const [utmForm, setUtmForm] = useState<UtmForm>(EMPTY_UTM);
  const [utmSaving, setUtmSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await listAdCampaigns();
      setCampaigns(data);
    } catch {
      setError('Failed to load campaigns');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    if (!newCampaign.name.trim()) return;
    setCreating(true);
    setError('');
    try {
      await createAdCampaign({
        name: newCampaign.name.trim(),
        description: newCampaign.description.trim() || null,
        meta_campaign_id: newCampaign.meta_campaign_id.trim() || null,
        meta_ad_set_id: newCampaign.meta_ad_set_id.trim() || null,
        is_attora_managed: true,
        is_active: true,
      });
      setNewCampaign(EMPTY_NEW);
      await load();
    } catch (e: unknown) {
      const msg =
        e && typeof e === 'object' && 'response' in e
          ? // @ts-expect-error axios response shape
            e.response?.data?.detail ?? 'Failed to register campaign'
          : 'Failed to register campaign';
      setError(String(msg));
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(campaignId: string) {
    if (!confirm('Unregister this campaign? Leads tied to it will be unlinked.'))
      return;
    setError('');
    try {
      await deleteAdCampaign(campaignId);
      await load();
    } catch {
      setError('Failed to unregister campaign');
    }
  }

  function openUtmEditor(campaign: AdCampaign) {
    setUtmTarget(campaign.id);
    setUtmForm({
      product_page_url: campaign.utm?.product_page_url ?? '',
      checkout_url: campaign.utm?.checkout_url ?? '',
      success_url: campaign.utm?.success_url ?? '',
    });
  }

  async function handleGenerateUtms(event: React.FormEvent) {
    event.preventDefault();
    if (!utmTarget) return;
    if (
      !utmForm.product_page_url &&
      !utmForm.checkout_url &&
      !utmForm.success_url
    ) {
      setError('At least one URL is required to generate UTMs.');
      return;
    }
    setUtmSaving(true);
    setError('');
    try {
      await generateCampaignUtms(utmTarget, {
        product_page_url: utmForm.product_page_url.trim() || null,
        checkout_url: utmForm.checkout_url.trim() || null,
        success_url: utmForm.success_url.trim() || null,
      });
      setUtmTarget(null);
      setUtmForm(EMPTY_UTM);
      await load();
    } catch (e: unknown) {
      const msg =
        e && typeof e === 'object' && 'response' in e
          ? // @ts-expect-error axios response shape
            e.response?.data?.detail ?? 'Failed to generate UTMs'
          : 'Failed to generate UTMs';
      setError(String(msg));
    } finally {
      setUtmSaving(false);
    }
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Attora Campaigns</h1>
        <p className="mt-1 text-sm text-gray-500">
          Register the ad campaigns Attora is authorized to act on. Leads arriving
          via unregistered campaigns are flagged but not contacted.
        </p>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <form
        onSubmit={handleCreate}
        className="mb-6 grid gap-3 rounded-xl border border-gray-200 bg-white p-4 md:grid-cols-2"
      >
        <div className="md:col-span-2">
          <h2 className="text-sm font-semibold text-gray-900">Register campaign</h2>
        </div>
        <input
          className="rounded-md border border-gray-300 px-3 py-2 text-sm"
          placeholder="Internal name"
          value={newCampaign.name}
          onChange={(e) =>
            setNewCampaign({ ...newCampaign, name: e.target.value })
          }
          required
        />
        <input
          className="rounded-md border border-gray-300 px-3 py-2 text-sm"
          placeholder="Meta campaign ID"
          value={newCampaign.meta_campaign_id}
          onChange={(e) =>
            setNewCampaign({ ...newCampaign, meta_campaign_id: e.target.value })
          }
        />
        <input
          className="rounded-md border border-gray-300 px-3 py-2 text-sm"
          placeholder="Meta ad set ID (optional)"
          value={newCampaign.meta_ad_set_id}
          onChange={(e) =>
            setNewCampaign({ ...newCampaign, meta_ad_set_id: e.target.value })
          }
        />
        <input
          className="rounded-md border border-gray-300 px-3 py-2 text-sm"
          placeholder="Description (optional)"
          value={newCampaign.description}
          onChange={(e) =>
            setNewCampaign({ ...newCampaign, description: e.target.value })
          }
        />
        <div className="md:col-span-2">
          <button
            type="submit"
            disabled={creating}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
          >
            {creating ? 'Registering...' : 'Register'}
          </button>
        </div>
      </form>

      {loading ? (
        <LoadingSpinner className="mt-12" />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50">
              <tr className="text-left text-gray-600">
                <th className="px-4 py-3 font-medium">Campaign</th>
                <th className="px-4 py-3 font-medium">Meta ID</th>
                <th className="px-4 py-3 font-medium">Managed</th>
                <th className="px-4 py-3 font-medium">UTM set</th>
                <th className="px-4 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.length === 0 ? (
                <tr>
                  <td className="px-4 py-6 text-gray-500" colSpan={5}>
                    No campaigns registered.
                  </td>
                </tr>
              ) : (
                campaigns.map((c) => (
                  <tr key={c.id} className="border-t border-gray-100 align-top">
                    <td className="px-4 py-3">
                      <div className="font-medium text-gray-900">{c.name}</div>
                      {c.description && (
                        <div className="text-xs text-gray-500">{c.description}</div>
                      )}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-700">
                      {c.meta_campaign_id ?? '-'}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={
                          c.is_attora_managed && c.is_active
                            ? 'rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800'
                            : 'rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-700'
                        }
                      >
                        {c.is_attora_managed && c.is_active ? 'Active' : 'Paused'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-700">
                      {c.utm ? (
                        <div className="space-y-1">
                          {c.utm.product_page_utm_url && (
                            <div>
                              <span className="text-gray-500">product:</span>{' '}
                              <a
                                className="break-all text-blue-600 hover:underline"
                                href={c.utm.product_page_utm_url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                {c.utm.product_page_utm_url}
                              </a>
                            </div>
                          )}
                          {c.utm.checkout_utm_url && (
                            <div>
                              <span className="text-gray-500">checkout:</span>{' '}
                              <a
                                className="break-all text-blue-600 hover:underline"
                                href={c.utm.checkout_utm_url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                {c.utm.checkout_utm_url}
                              </a>
                            </div>
                          )}
                          {c.utm.success_utm_url && (
                            <div>
                              <span className="text-gray-500">success:</span>{' '}
                              <a
                                className="break-all text-blue-600 hover:underline"
                                href={c.utm.success_utm_url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                {c.utm.success_utm_url}
                              </a>
                            </div>
                          )}
                        </div>
                      ) : (
                        <span className="text-gray-400">None</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => openUtmEditor(c)}
                        className="mr-2 rounded-md border border-gray-300 px-3 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50"
                      >
                        {c.utm ? 'Edit UTMs' : 'Generate UTMs'}
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleDelete(c.id)}
                        className="rounded-md border border-red-200 px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-50"
                      >
                        Unregister
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {utmTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <form
            onSubmit={handleGenerateUtms}
            className="w-full max-w-lg space-y-3 rounded-xl bg-white p-6 shadow-xl"
          >
            <h2 className="text-lg font-semibold text-gray-900">
              Generate UTM URLs
            </h2>
            <p className="text-xs text-gray-500">
              We'll append utm_source=attora, utm_medium=messaging, and a utm_campaign
              slug derived from the campaign name to each URL below.
            </p>
            <div>
              <label className="block text-xs font-medium text-gray-700">
                Product page URL
              </label>
              <input
                className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                placeholder="https://shop.example.com/products/abc"
                value={utmForm.product_page_url}
                onChange={(e) =>
                  setUtmForm({ ...utmForm, product_page_url: e.target.value })
                }
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700">
                Checkout URL
              </label>
              <input
                className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                placeholder="https://shop.example.com/checkout/abc"
                value={utmForm.checkout_url}
                onChange={(e) =>
                  setUtmForm({ ...utmForm, checkout_url: e.target.value })
                }
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700">
                Purchase success URL
              </label>
              <input
                className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                placeholder="https://shop.example.com/thank-you"
                value={utmForm.success_url}
                onChange={(e) =>
                  setUtmForm({ ...utmForm, success_url: e.target.value })
                }
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => {
                  setUtmTarget(null);
                  setUtmForm(EMPTY_UTM);
                }}
                className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={utmSaving}
                className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
              >
                {utmSaving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
