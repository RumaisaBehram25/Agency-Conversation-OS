import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createAdCampaign,
  deleteAdCampaign,
  generateCampaignUtms,
  getCampaignUtmForSubscriber,
  listAdCampaigns,
  updateAdCampaign,
} from '../api/campaigns';
import { lookupAdCampaignId } from '../api/settings';
import { getProducts } from '../api/products';
import type { AdCampaign, CampaignSourceType, CampaignUTM } from '../types';
import LoadingSpinner from '../components/ui/LoadingSpinner';

interface NewCampaignForm {
  name: string;
  description: string;
  meta_campaign_id: string;
  meta_ad_set_id: string;
  product_id: string;
  source_type: CampaignSourceType;
  keyword: string;
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
  product_id: '',
  source_type: 'paid',
  keyword: '',
};

type SourceFilter = 'all' | CampaignSourceType;

const EMPTY_UTM: UtmForm = {
  product_page_url: '',
  checkout_url: '',
  success_url: '',
};

export default function CampaignsPage() {
  const queryClient = useQueryClient();
  const [error, setError] = useState('');

  const [newCampaign, setNewCampaign] = useState<NewCampaignForm>(EMPTY_NEW);
  const [creating, setCreating] = useState(false);

  const [utmTarget, setUtmTarget] = useState<string | null>(null);
  const [utmForm, setUtmForm] = useState<UtmForm>(EMPTY_UTM);
  const [utmSaving, setUtmSaving] = useState(false);

  const [viewUtmTarget, setViewUtmTarget] = useState<AdCampaign | null>(null);
  const [previewSubscriberId, setPreviewSubscriberId] = useState('');
  const [previewUtm, setPreviewUtm] = useState<CampaignUTM | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState('');

  const [pageSize, setPageSize] = useState(25);
  const [currentPage, setCurrentPage] = useState(1);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all');
  const [editingKeywordId, setEditingKeywordId] = useState<string | null>(null);
  const [keywordDraft, setKeywordDraft] = useState('');
  const [keywordSaving, setKeywordSaving] = useState(false);

  const [editingMetaIdFor, setEditingMetaIdFor] = useState<string | null>(null);
  const [metaIdDraft, setMetaIdDraft] = useState('');
  const [metaIdSaving, setMetaIdSaving] = useState(false);

  const [lookupAdId, setLookupAdId] = useState('');
  const [lookupResult, setLookupResult] = useState<{ ad_id: string; campaign_id: string } | null>(null);
  const [lookupError, setLookupError] = useState('');
  const [lookupLoading, setLookupLoading] = useState(false);
  const [lookupCopied, setLookupCopied] = useState(false);

  async function saveKeyword(campaignId: string) {
    const trimmed = keywordDraft.trim().toUpperCase();
    if (!trimmed) {
      setError('Keyword is required for organic campaigns.');
      return;
    }
    setKeywordSaving(true);
    setError('');
    try {
      await updateAdCampaign(campaignId, { keyword: trimmed });
      setEditingKeywordId(null);
      setKeywordDraft('');
      await load();
    } catch (e: unknown) {
      const msg =
        e && typeof e === 'object' && 'response' in e
          ? // @ts-expect-error axios response shape
            e.response?.data?.detail ?? 'Failed to update keyword'
          : 'Failed to update keyword';
      setError(String(msg));
    } finally {
      setKeywordSaving(false);
    }
  }

  async function saveMetaCampaignId(campaignId: string) {
    const trimmed = metaIdDraft.trim();
    setMetaIdSaving(true);
    setError('');
    try {
      await updateAdCampaign(campaignId, { meta_campaign_id: trimmed || null });
      setEditingMetaIdFor(null);
      setMetaIdDraft('');
      await load();
    } catch (e: unknown) {
      const msg =
        e && typeof e === 'object' && 'response' in e
          ? // @ts-expect-error axios response shape
            e.response?.data?.detail ?? 'Failed to update campaign ID'
          : 'Failed to update campaign ID';
      setError(String(msg));
    } finally {
      setMetaIdSaving(false);
    }
  }

  async function handleLookupAd() {
    const trimmed = lookupAdId.trim();
    if (!trimmed) return;
    setLookupLoading(true);
    setLookupError('');
    setLookupResult(null);
    setLookupCopied(false);
    try {
      const result = await lookupAdCampaignId(trimmed);
      setLookupResult(result);
    } catch (e: unknown) {
      const msg =
        e && typeof e === 'object' && 'response' in e
          ? // @ts-expect-error axios response shape
            e.response?.data?.detail ?? 'Lookup failed'
          : 'Lookup failed';
      setLookupError(String(msg));
    } finally {
      setLookupLoading(false);
    }
  }

  function copyCampaignId(id: string) {
    void navigator.clipboard.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId((current) => (current === id ? null : current)), 1500);
  }

  const {
    data: campaigns = [],
    isLoading: loading,
    isError: campaignsError,
  } = useQuery({
    queryKey: ['ad-campaigns'],
    queryFn: () => listAdCampaigns(),
  });

  const { data: products = [] } = useQuery({
    queryKey: ['products'],
    queryFn: () => getProducts(),
  });

  async function handleAttachProduct(campaignId: string, productId: string) {
    setError('');
    try {
      await updateAdCampaign(campaignId, {
        product_id: productId || null,
      });
      await load();
    } catch (e: unknown) {
      const msg =
        e && typeof e === 'object' && 'response' in e
          ? // @ts-expect-error axios response shape
            e.response?.data?.detail ?? 'Failed to update product link'
          : 'Failed to update product link';
      setError(String(msg));
    }
  }

  async function load() {
    await queryClient.invalidateQueries({ queryKey: ['ad-campaigns'] });
  }

  useEffect(() => {
    if (campaignsError) setError('Failed to load campaigns');
  }, [campaignsError]);

  const filteredCampaigns =
    sourceFilter === 'all'
      ? campaigns
      : campaigns.filter((c) => c.source_type === sourceFilter);

  // Keep currentPage in bounds when the list shrinks (e.g., after unregister
  // or filter change) or the user changes page size.
  const totalPages = Math.max(1, Math.ceil(filteredCampaigns.length / pageSize));
  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages);
    }
  }, [currentPage, totalPages]);

  const pageStart = (currentPage - 1) * pageSize;
  const pageEnd = Math.min(pageStart + pageSize, filteredCampaigns.length);
  const paginatedCampaigns = filteredCampaigns.slice(pageStart, pageEnd);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    if (!newCampaign.name.trim()) return;
    const trimmedKeyword = newCampaign.keyword.trim().toUpperCase();
    if (newCampaign.source_type === 'organic' && !trimmedKeyword) {
      setError('Organic campaigns require a keyword (e.g. MUSCLE).');
      return;
    }
    setCreating(true);
    setError('');
    try {
      await createAdCampaign({
        name: newCampaign.name.trim(),
        description: newCampaign.description.trim() || null,
        meta_campaign_id:
          newCampaign.source_type === 'organic'
            ? null
            : newCampaign.meta_campaign_id.trim() || null,
        meta_ad_set_id:
          newCampaign.source_type === 'organic'
            ? null
            : newCampaign.meta_ad_set_id.trim() || null,
        product_id: newCampaign.product_id.trim() || null,
        source_type: newCampaign.source_type,
        keyword: trimmedKeyword || null,
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

  async function handleCreateDummy() {
    if (creating) return;
    setCreating(true);
    setError('');
    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    try {
      await createAdCampaign({
        name: `Dummy Test Campaign ${ts}`,
        description: 'Seeded for UTM + Playground testing.',
        meta_campaign_id: `dummy_${Date.now()}`,
        meta_ad_set_id: null,
        is_attora_managed: true,
        is_active: true,
      });
      await load();
    } catch (e: unknown) {
      const msg =
        e && typeof e === 'object' && 'response' in e
          ? // @ts-expect-error axios response shape
            e.response?.data?.detail ?? 'Failed to create dummy campaign'
          : 'Failed to create dummy campaign';
      setError(String(msg));
    } finally {
      setCreating(false);
    }
  }

  async function handlePreviewAsSubscriber() {
    if (!viewUtmTarget) return;
    const subId = previewSubscriberId.trim();
    if (!subId) {
      setPreviewError('Enter a subscriber ID to preview.');
      return;
    }
    setPreviewLoading(true);
    setPreviewError('');
    try {
      const result = await getCampaignUtmForSubscriber(viewUtmTarget.id, subId);
      setPreviewUtm(result);
    } catch (e: unknown) {
      const msg =
        e && typeof e === 'object' && 'response' in e
          ? // @ts-expect-error axios response shape
            e.response?.data?.detail ?? 'Preview failed'
          : 'Preview failed';
      setPreviewError(String(msg));
      setPreviewUtm(null);
    } finally {
      setPreviewLoading(false);
    }
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
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Attora Campaigns</h1>
          <p className="mt-1 text-sm text-gray-500">
            Register the ad campaigns Attora is authorized to act on. Leads arriving
            via unregistered campaigns are flagged but not contacted.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void handleCreateDummy()}
          disabled={creating}
          className="inline-flex items-center gap-1.5 rounded-md border border-dashed border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:border-primary-400 hover:bg-primary-50 hover:text-primary-700 disabled:opacity-60"
          title="Create a test campaign you can immediately use to generate UTMs and try the Playground."
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.75" stroke="currentColor" className="h-4 w-4">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          {creating ? 'Creating…' : 'Create dummy campaign'}
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Ad ID → Campaign ID lookup */}
      <div className="mb-4 rounded-xl border border-blue-100 bg-blue-50 p-4">
        <h2 className="mb-1 text-sm font-semibold text-blue-900">Find Campaign ID from Ad ID</h2>
        <p className="mb-3 text-xs text-blue-700">
          Paste the Ad ID from your spreadsheet to get the Campaign ID needed for registration.
        </p>
        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="e.g. 120246040273560659"
            value={lookupAdId}
            onChange={(e) => {
              setLookupAdId(e.target.value);
              setLookupResult(null);
              setLookupError('');
            }}
            onKeyDown={(e) => { if (e.key === 'Enter') void handleLookupAd(); }}
            className="flex-1 rounded-md border border-blue-200 bg-white px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-300"
          />
          <button
            type="button"
            onClick={() => void handleLookupAd()}
            disabled={lookupLoading || !lookupAdId.trim()}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {lookupLoading ? 'Looking up…' : 'Look up'}
          </button>
        </div>
        {lookupError && (
          <p className="mt-2 text-xs text-red-700">{lookupError}</p>
        )}
        {lookupResult && (
          <div className="mt-3 flex items-center gap-3 rounded-lg border border-blue-200 bg-white px-3 py-2">
            <div className="flex-1">
              <p className="text-xs text-gray-500">Campaign ID for ad <span className="font-mono">{lookupResult.ad_id}</span></p>
              <p className="mt-0.5 font-mono text-sm font-semibold text-gray-900">{lookupResult.campaign_id}</p>
            </div>
            <button
              type="button"
              onClick={() => {
                void navigator.clipboard.writeText(lookupResult.campaign_id);
                setLookupCopied(true);
                setTimeout(() => setLookupCopied(false), 1500);
              }}
              className="shrink-0 rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
            >
              {lookupCopied ? 'Copied!' : 'Copy'}
            </button>
            <button
              type="button"
              onClick={() => {
                setNewCampaign({ ...newCampaign, meta_campaign_id: lookupResult.campaign_id, source_type: 'paid' });
                setLookupResult(null);
                setLookupAdId('');
              }}
              className="shrink-0 rounded-md border border-blue-300 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-100"
            >
              Use in register form
            </button>
            <button
              type="button"
              onClick={() => {
                setMetaIdDraft(lookupResult.campaign_id);
                setLookupResult(null);
                setLookupAdId('');
              }}
              className="shrink-0 rounded-md border border-emerald-300 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-100"
            >
              Add to organic campaign
            </button>
          </div>
        )}
      </div>

      <form
        onSubmit={handleCreate}
        className="mb-6 grid gap-3 rounded-xl border border-gray-200 bg-white p-4 md:grid-cols-2"
      >
        <div className="md:col-span-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-gray-900">Register campaign</h2>
          <div
            role="radiogroup"
            aria-label="Campaign source"
            className="inline-flex overflow-hidden rounded-md border border-gray-300 bg-white text-xs font-medium"
          >
            <button
              type="button"
              role="radio"
              aria-checked={newCampaign.source_type === 'paid'}
              onClick={() =>
                setNewCampaign({ ...newCampaign, source_type: 'paid' })
              }
              className={
                newCampaign.source_type === 'paid'
                  ? 'bg-blue-600 px-3 py-1.5 text-white'
                  : 'bg-white px-3 py-1.5 text-gray-700 hover:bg-gray-50'
              }
            >
              Paid Ad
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={newCampaign.source_type === 'organic'}
              onClick={() =>
                setNewCampaign({ ...newCampaign, source_type: 'organic' })
              }
              className={
                newCampaign.source_type === 'organic'
                  ? 'bg-emerald-600 px-3 py-1.5 text-white'
                  : 'bg-white px-3 py-1.5 text-gray-700 hover:bg-gray-50'
              }
            >
              Organic Post
            </button>
          </div>
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
        {newCampaign.source_type === 'organic' ? (
          <input
            className="rounded-md border border-gray-300 px-3 py-2 text-sm font-mono uppercase"
            placeholder="Trigger keyword (e.g. MUSCLE)"
            value={newCampaign.keyword}
            onChange={(e) =>
              setNewCampaign({
                ...newCampaign,
                keyword: e.target.value.toUpperCase(),
              })
            }
            required
            aria-label="Keyword"
            title="The exact ManyChat trigger keyword (case-insensitive). Must be unique within the org."
          />
        ) : (
          <input
            className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            placeholder="Meta campaign ID"
            value={newCampaign.meta_campaign_id}
            onChange={(e) =>
              setNewCampaign({ ...newCampaign, meta_campaign_id: e.target.value })
            }
          />
        )}
        {newCampaign.source_type === 'paid' && (
          <input
            className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            placeholder="Meta ad set ID (optional)"
            value={newCampaign.meta_ad_set_id}
            onChange={(e) =>
              setNewCampaign({ ...newCampaign, meta_ad_set_id: e.target.value })
            }
          />
        )}
        <input
          className="rounded-md border border-gray-300 px-3 py-2 text-sm"
          placeholder="Description (optional)"
          value={newCampaign.description}
          onChange={(e) =>
            setNewCampaign({ ...newCampaign, description: e.target.value })
          }
        />
        <select
          className="rounded-md border border-gray-300 px-3 py-2 text-sm"
          value={newCampaign.product_id}
          onChange={(e) =>
            setNewCampaign({ ...newCampaign, product_id: e.target.value })
          }
        >
          <option value="">No product linked</option>
          {products.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
              {p.price ? ` — $${p.price}` : ''}
            </option>
          ))}
        </select>
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

      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <span className="text-gray-500">Show:</span>
        {(['all', 'paid', 'organic'] as const).map((opt) => {
          const count =
            opt === 'all'
              ? campaigns.length
              : campaigns.filter((c) => c.source_type === opt).length;
          const active = sourceFilter === opt;
          return (
            <button
              key={opt}
              type="button"
              onClick={() => {
                setSourceFilter(opt);
                setCurrentPage(1);
              }}
              className={
                active
                  ? 'rounded-full bg-gray-900 px-3 py-1 font-medium text-white'
                  : 'rounded-full border border-gray-300 bg-white px-3 py-1 font-medium text-gray-700 hover:bg-gray-50'
              }
            >
              {opt === 'all' ? 'All' : opt === 'paid' ? 'Paid' : 'Organic'}
              <span className={active ? 'ml-1.5 text-gray-300' : 'ml-1.5 text-gray-400'}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {loading ? (
        <LoadingSpinner className="mt-12" />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50">
              <tr className="text-left text-gray-600">
                <th className="px-4 py-3 font-medium">Campaign</th>
                <th className="px-4 py-3 font-medium">Source</th>
                <th className="px-4 py-3 font-medium">Attora ID</th>
                <th className="px-4 py-3 font-medium">Product</th>
                <th className="px-4 py-3 font-medium">Meta ID / Keyword</th>
                <th className="px-4 py-3 font-medium">Managed</th>
                <th className="px-4 py-3 font-medium">UTM set</th>
                <th className="min-w-[11rem] whitespace-nowrap px-4 py-3 text-right font-medium">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {filteredCampaigns.length === 0 ? (
                <tr>
                  <td className="px-4 py-6 text-gray-500" colSpan={8}>
                    {sourceFilter === 'all'
                      ? 'No campaigns registered.'
                      : `No ${sourceFilter} campaigns.`}
                  </td>
                </tr>
              ) : (
                paginatedCampaigns.map((c) => (
                  <tr key={c.id} className="border-t border-gray-100 align-top">
                    <td className="px-4 py-3">
                      <div className="font-medium text-gray-900">{c.name}</div>
                      {c.description && (
                        <div className="text-xs text-gray-500">{c.description}</div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={
                          c.source_type === 'organic'
                            ? 'rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800'
                            : 'rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800'
                        }
                      >
                        {c.source_type === 'organic' ? 'Organic' : 'Paid'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        onClick={() => copyCampaignId(c.id)}
                        title={`Click to copy: ${c.id}`}
                        className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1 font-mono text-xs text-gray-700 hover:bg-gray-100"
                      >
                        {copiedId === c.id ? 'Copied!' : `${c.id.slice(0, 8)}…`}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <select
                        value={c.product_id ?? ''}
                        onChange={(e) => void handleAttachProduct(c.id, e.target.value)}
                        className="max-w-[14rem] rounded-md border border-gray-300 bg-white px-2 py-1 text-xs"
                      >
                        <option value="">— None —</option>
                        {products.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name}
                            {p.price ? ` — $${p.price}` : ''}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-700">
                      {c.source_type === 'organic' ? (
                        <div className="flex flex-col gap-1.5">
                          {/* Keyword */}
                          {editingKeywordId === c.id ? (
                            <div className="flex items-center gap-1">
                              <input
                                autoFocus
                                type="text"
                                value={keywordDraft}
                                onChange={(e) => setKeywordDraft(e.target.value.toUpperCase())}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') void saveKeyword(c.id);
                                  if (e.key === 'Escape') { setEditingKeywordId(null); setKeywordDraft(''); }
                                }}
                                disabled={keywordSaving}
                                placeholder="MUSCLE"
                                className="w-24 rounded-md border border-gray-300 bg-white px-2 py-1 font-mono text-xs uppercase focus:border-emerald-400 focus:outline-none focus:ring-1 focus:ring-emerald-300"
                              />
                              <button type="button" onClick={() => void saveKeyword(c.id)} disabled={keywordSaving} className="rounded-md border border-emerald-300 bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700 hover:bg-emerald-100 disabled:opacity-60">{keywordSaving ? '…' : 'Save'}</button>
                              <button type="button" onClick={() => { setEditingKeywordId(null); setKeywordDraft(''); }} disabled={keywordSaving} className="rounded-md border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50">✕</button>
                            </div>
                          ) : (
                            <button
                              type="button"
                              onClick={() => { setEditingKeywordId(c.id); setKeywordDraft(c.keyword ?? ''); }}
                              className={c.keyword ? 'rounded-md border border-gray-200 bg-emerald-50 px-2 py-1 font-mono text-xs text-emerald-800 hover:border-emerald-400' : 'rounded-md border border-dashed border-amber-300 bg-amber-50 px-2 py-1 text-xs font-medium text-amber-800 hover:border-amber-500'}
                              title={c.keyword ? 'Click to edit keyword' : 'Click to add keyword'}
                            >
                              {c.keyword ?? '+ Add keyword'}
                            </button>
                          )}
                          {/* Boost / Meta Campaign ID */}
                          {editingMetaIdFor === c.id ? (
                            <div className="flex items-center gap-1">
                              <input
                                autoFocus
                                type="text"
                                value={metaIdDraft}
                                onChange={(e) => setMetaIdDraft(e.target.value.trim())}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') void saveMetaCampaignId(c.id);
                                  if (e.key === 'Escape') { setEditingMetaIdFor(null); setMetaIdDraft(''); }
                                }}
                                disabled={metaIdSaving}
                                placeholder="Campaign ID"
                                className="w-36 rounded-md border border-gray-300 bg-white px-2 py-1 font-mono text-xs focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-300"
                              />
                              <button type="button" onClick={() => void saveMetaCampaignId(c.id)} disabled={metaIdSaving} className="rounded-md border border-blue-300 bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-60">{metaIdSaving ? '…' : 'Save'}</button>
                              <button type="button" onClick={() => { setEditingMetaIdFor(null); setMetaIdDraft(''); }} disabled={metaIdSaving} className="rounded-md border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50">✕</button>
                            </div>
                          ) : (
                            <button
                              type="button"
                              onClick={() => { setEditingMetaIdFor(c.id); setMetaIdDraft(c.meta_campaign_id ?? ''); }}
                              className={c.meta_campaign_id ? 'rounded-md border border-gray-200 bg-blue-50 px-2 py-1 font-mono text-xs text-blue-800 hover:border-blue-400' : 'rounded-md border border-dashed border-blue-200 bg-white px-2 py-1 text-xs font-medium text-blue-500 hover:border-blue-400'}
                              title={c.meta_campaign_id ? 'Click to edit boost campaign ID' : 'Click to add boost campaign ID'}
                            >
                              {c.meta_campaign_id ?? '+ Add boost ID'}
                            </button>
                          )}
                        </div>
                      ) : (
                        c.meta_campaign_id ?? '-'
                      )}
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
                    <td className="px-4 py-3">
                      {c.utm ? (
                        <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800">
                          Set
                        </span>
                      ) : (
                        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
                          None
                        </span>
                      )}
                    </td>
                    <td className="min-w-[13rem] align-top px-4 py-3">
                      <div className="flex items-start justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => openUtmEditor(c)}
                          className="whitespace-nowrap rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
                        >
                          {c.utm ? 'Edit UTMs' : 'Generate UTMs'}
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setViewUtmTarget(c);
                            setPreviewSubscriberId('');
                            setPreviewUtm(null);
                            setPreviewError('');
                          }}
                          disabled={!c.utm}
                          title={c.utm ? 'View UTM URLs' : 'No UTMs to view'}
                          aria-label="View UTM URLs"
                          className="rounded-md border border-gray-300 p-1.5 text-gray-600 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            fill="none"
                            viewBox="0 0 24 24"
                            strokeWidth="1.5"
                            stroke="currentColor"
                            className="h-4 w-4"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z"
                            />
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                            />
                          </svg>
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleDelete(c.id)}
                          className="whitespace-nowrap rounded-md border border-red-200 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50"
                        >
                          Unregister
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>

          {filteredCampaigns.length > 0 && (
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-gray-100 bg-gray-50 px-4 py-3 text-sm text-gray-700">
              <div className="flex items-center gap-2">
                <span>Rows per page:</span>
                <select
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(Number(e.target.value));
                    setCurrentPage(1);
                  }}
                  className="rounded-md border border-gray-300 bg-white px-2 py-1 text-xs"
                >
                  <option value={10}>10</option>
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                </select>
              </div>

              <div className="text-xs text-gray-600">
                Showing <span className="font-medium">{pageStart + 1}</span>–
                <span className="font-medium">{pageEnd}</span> of{' '}
                <span className="font-medium">{filteredCampaigns.length}</span>
              </div>

              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setCurrentPage(1)}
                  disabled={currentPage === 1}
                  className="rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
                  aria-label="First page"
                >
                  «
                </button>
                <button
                  type="button"
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="rounded-md border border-gray-300 px-3 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Prev
                </button>
                <span className="px-2 text-xs tabular-nums text-gray-600">
                  Page {currentPage} / {totalPages}
                </span>
                <button
                  type="button"
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="rounded-md border border-gray-300 px-3 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Next
                </button>
                <button
                  type="button"
                  onClick={() => setCurrentPage(totalPages)}
                  disabled={currentPage === totalPages}
                  className="rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
                  aria-label="Last page"
                >
                  »
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {viewUtmTarget && viewUtmTarget.utm && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 sm:items-center"
          onClick={() => setViewUtmTarget(null)}
        >
          <div
            className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-xl bg-white shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Sticky header */}
            <div className="flex items-start justify-between gap-4 border-b border-gray-100 px-6 py-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">UTM URLs</h2>
                <p className="mt-0.5 text-sm text-gray-500">{viewUtmTarget.name}</p>
              </div>
              <button
                type="button"
                onClick={() => setViewUtmTarget(null)}
                className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                aria-label="Close"
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor" className="h-5 w-5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Scrollable body */}
            <div className="flex-1 space-y-4 overflow-y-auto px-6 py-4">

            <div className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 text-xs text-gray-600">
              <div>
                <span className="text-gray-500">utm_source:</span>{' '}
                <span className="font-mono text-gray-900">{viewUtmTarget.utm.utm_source}</span>
              </div>
              <div>
                <span className="text-gray-500">utm_medium:</span>{' '}
                <span className="font-mono text-gray-900">{viewUtmTarget.utm.utm_medium}</span>
              </div>
              <div>
                <span className="text-gray-500">utm_campaign:</span>{' '}
                <span className="font-mono text-gray-900">{viewUtmTarget.utm.utm_campaign}</span>
              </div>
            </div>

            {/* Per-subscriber preview input — stamps attora_sub=<id> on each URL */}
            <div className="rounded-lg border border-blue-100 bg-blue-50 p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wider text-blue-800">
                    Preview as subscriber
                  </div>
                  <p className="mt-0.5 text-[11px] text-blue-700">
                    Appends <span className="font-mono">attora_sub=&lt;id&gt;</span> to each URL
                    — same stamping the AI does at reply time.
                  </p>
                </div>
                {previewUtm && (
                  <button
                    type="button"
                    onClick={() => {
                      setPreviewUtm(null);
                      setPreviewSubscriberId('');
                      setPreviewError('');
                    }}
                    className="shrink-0 rounded-md border border-blue-300 bg-white px-2 py-1 text-xs font-medium text-blue-700 hover:bg-blue-100"
                  >
                    Clear preview
                  </button>
                )}
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  placeholder="subscriber id (e.g. ig_reply_check)"
                  value={previewSubscriberId}
                  onChange={(e) => setPreviewSubscriberId(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void handlePreviewAsSubscriber();
                  }}
                  className="flex-1 rounded-md border border-blue-200 bg-white px-3 py-1.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-300"
                />
                <button
                  type="button"
                  onClick={() => void handlePreviewAsSubscriber()}
                  disabled={previewLoading || !previewSubscriberId.trim()}
                  className="shrink-0 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {previewLoading ? 'Loading…' : 'Preview'}
                </button>
              </div>
              {previewError && (
                <div className="mt-2 text-xs text-red-700">{previewError}</div>
              )}
              {previewUtm && (
                <div className="mt-2 text-[11px] font-medium text-blue-800">
                  Showing URLs tagged for <span className="font-mono">{previewSubscriberId.trim()}</span>
                </div>
              )}
            </div>

            {(() => {
              const src = previewUtm ?? viewUtmTarget.utm;
              return ([
                ['Product page', src.product_page_url, src.product_page_utm_url],
                ['Checkout', src.checkout_url, src.checkout_utm_url],
                ['Purchase success', src.success_url, src.success_utm_url],
              ] as const)
                .filter(([, , generated]) => !!generated)
                .map(([label, base, generated]) => (
                <div key={label} className="space-y-1 rounded-lg border border-gray-200 p-3">
                  <div className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                    {label}
                  </div>
                  {base && (
                    <div className="text-xs text-gray-500">
                      <span className="font-medium">Base:</span>{' '}
                      <span className="font-mono break-all">{base}</span>
                    </div>
                  )}
                  <div className="flex items-start gap-2">
                    <a
                      href={generated ?? undefined}
                      target="_blank"
                      rel="noreferrer"
                      className="flex-1 break-all rounded bg-blue-50 px-2 py-1.5 font-mono text-xs text-blue-700 hover:underline"
                    >
                      {generated}
                    </a>
                    <button
                      type="button"
                      onClick={() => {
                        if (generated) void navigator.clipboard.writeText(generated);
                      }}
                      className="shrink-0 rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50"
                    >
                      Copy
                    </button>
                  </div>
                </div>
              ));
            })()}
            </div>

            {/* Sticky footer */}
            <div className="flex justify-end border-t border-gray-100 px-6 py-3">
              <button
                type="button"
                onClick={() => setViewUtmTarget(null)}
                className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Close
              </button>
            </div>
          </div>
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
