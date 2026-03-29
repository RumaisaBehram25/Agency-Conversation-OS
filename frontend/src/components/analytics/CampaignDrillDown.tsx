import { useEffect, useState } from 'react';
import { getCampaignAdSets, getAdSetAds } from '../../api/campaigns';
import type { CampaignSummary, AdSetSummary, AdSummary } from '../../types';
import { formatCurrency, formatNumber, formatPercent } from '../../utils/formatters';
import Badge from '../ui/Badge';
import LoadingSpinner from '../ui/LoadingSpinner';

interface CampaignDrillDownProps {
  campaignId: string;
  dateFrom: string;
  dateTo: string;
  campaign: CampaignSummary;
}

function statusBadgeColor(status: string | null): 'green' | 'yellow' | 'gray' | 'red' {
  if (!status) return 'gray';
  const map: Record<string, 'green' | 'yellow' | 'gray' | 'red'> = {
    active: 'green',
    paused: 'yellow',
    deleted: 'red',
    archived: 'gray',
  };
  return map[status.toLowerCase()] || 'gray';
}

function fmtNullable(value: number | null, formatter: (v: number) => string, fallback = '--'): string {
  return value != null ? formatter(value) : fallback;
}

export default function CampaignDrillDown({
  campaignId,
  dateFrom,
  dateTo,
  campaign,
}: CampaignDrillDownProps) {
  const [adSets, setAdSets] = useState<AdSetSummary[]>([]);
  const [loadingAdSets, setLoadingAdSets] = useState(true);
  const [adSetsError, setAdSetsError] = useState('');

  // Track which ad set is expanded, and cache ads per ad set
  const [expandedAdSetId, setExpandedAdSetId] = useState<string | null>(null);
  const [adsMap, setAdsMap] = useState<Record<string, AdSummary[]>>({});
  const [loadingAds, setLoadingAds] = useState<string | null>(null);
  const [adsError, setAdsError] = useState('');

  // Fetch ad sets when campaign or date range changes
  useEffect(() => {
    setLoadingAdSets(true);
    setAdSetsError('');
    setExpandedAdSetId(null);
    setAdsMap({});
    getCampaignAdSets(campaignId, { date_from: dateFrom, date_to: dateTo })
      .then(setAdSets)
      .catch(() => setAdSetsError('Failed to load ad sets'))
      .finally(() => setLoadingAdSets(false));
  }, [campaignId, dateFrom, dateTo]);

  // Handle ad set row click
  function handleAdSetClick(adsetId: string) {
    if (expandedAdSetId === adsetId) {
      setExpandedAdSetId(null);
      return;
    }
    setExpandedAdSetId(adsetId);
    setAdsError('');

    // If already cached, don't refetch
    if (adsMap[adsetId]) return;

    setLoadingAds(adsetId);
    getAdSetAds(campaignId, adsetId, { date_from: dateFrom, date_to: dateTo })
      .then((ads) => {
        setAdsMap((prev) => ({ ...prev, [adsetId]: ads }));
      })
      .catch(() => setAdsError('Failed to load ads'))
      .finally(() => setLoadingAds(null));
  }

  return (
    <div className="space-y-6">
      {/* Campaign Summary Card */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">
              {campaign.meta_campaign_name || 'Unnamed Campaign'}
            </h3>
            <div className="mt-1 flex items-center gap-3">
              {campaign.status && (
                <Badge color={statusBadgeColor(campaign.status)}>
                  {campaign.status.charAt(0).toUpperCase() + campaign.status.slice(1)}
                </Badge>
              )}
              {campaign.status && (
                <span className="text-sm text-gray-500">Campaign</span>
              )}
            </div>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wider">Spend</p>
            <p className="mt-1 text-lg font-bold text-gray-900">
              {formatCurrency(campaign.spend)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wider">Impressions</p>
            <p className="mt-1 text-lg font-bold text-gray-900">
              {formatNumber(campaign.impressions)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wider">Clicks</p>
            <p className="mt-1 text-lg font-bold text-gray-900">
              {formatNumber(campaign.clicks)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wider">Leads</p>
            <p className="mt-1 text-lg font-bold text-gray-900">
              {formatNumber(campaign.leads)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wider">CPC</p>
            <p className="mt-1 text-lg font-bold text-gray-900">
              {fmtNullable(campaign.cpc, formatCurrency)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wider">CTR</p>
            <p className="mt-1 text-lg font-bold text-gray-900">
              {fmtNullable(campaign.ctr, (v) => formatPercent(v))}
            </p>
          </div>
        </div>
      </div>

      {/* Ad Sets Table */}
      <div>
        <h3 className="mb-3 text-sm font-semibold text-gray-900">Ad Sets</h3>
        {loadingAdSets ? (
          <LoadingSpinner className="mt-6" />
        ) : adSetsError ? (
          <div className="mt-4 text-center text-sm text-red-600">{adSetsError}</div>
        ) : adSets.length === 0 ? (
          <div className="py-8 text-center text-sm text-gray-400">
            No ad sets found for this campaign
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Name
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                    Spend
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                    Impressions
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                    Clicks
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                    Leads
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                    CPC
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                    CTR
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                    Link Clicks
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                    Video Views
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {adSets.map((adSet) => {
                  const isExpanded = expandedAdSetId === adSet.meta_adset_id;
                  const ads = adsMap[adSet.meta_adset_id];
                  const isLoadingThisAds = loadingAds === adSet.meta_adset_id;

                  return (
                    <AdSetRow
                      key={adSet.meta_adset_id}
                      adSet={adSet}
                      isExpanded={isExpanded}
                      ads={ads}
                      isLoadingAds={isLoadingThisAds}
                      adsError={isExpanded ? adsError : ''}
                      onClick={() => handleAdSetClick(adSet.meta_adset_id)}
                    />
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Ad Set Row (with nested ads) ─────────────────────────────────────────── */

interface AdSetRowProps {
  adSet: AdSetSummary;
  isExpanded: boolean;
  ads: AdSummary[] | undefined;
  isLoadingAds: boolean;
  adsError: string;
  onClick: () => void;
}

function AdSetRow({ adSet, isExpanded, ads, isLoadingAds, adsError, onClick }: AdSetRowProps) {
  return (
    <>
      <tr
        onClick={onClick}
        className="cursor-pointer transition-colors hover:bg-gray-50"
      >
        <td className="whitespace-nowrap px-6 py-4">
          <div className="flex items-center gap-2">
            <svg
              className={`h-4 w-4 flex-shrink-0 text-gray-400 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth="2"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
            </svg>
            <span className="text-sm font-medium text-gray-900">
              {adSet.meta_adset_name || 'Unnamed Ad Set'}
            </span>
          </div>
        </td>
        <td className="whitespace-nowrap px-4 py-4 text-right text-sm text-gray-700">
          {formatCurrency(adSet.spend)}
        </td>
        <td className="whitespace-nowrap px-4 py-4 text-right text-sm text-gray-700">
          {formatNumber(adSet.impressions)}
        </td>
        <td className="whitespace-nowrap px-4 py-4 text-right text-sm text-gray-700">
          {formatNumber(adSet.clicks)}
        </td>
        <td className="whitespace-nowrap px-4 py-4 text-right text-sm text-gray-700">
          {formatNumber(adSet.leads)}
        </td>
        <td className="whitespace-nowrap px-4 py-4 text-right text-sm text-gray-700">
          {fmtNullable(adSet.cpc, formatCurrency)}
        </td>
        <td className="whitespace-nowrap px-4 py-4 text-right text-sm text-gray-700">
          {fmtNullable(adSet.ctr, (v) => formatPercent(v))}
        </td>
        <td className="whitespace-nowrap px-4 py-4 text-right text-sm text-gray-700">
          {formatNumber(adSet.link_clicks)}
        </td>
        <td className="whitespace-nowrap px-4 py-4 text-right text-sm text-gray-700">
          {formatNumber(adSet.video_views)}
        </td>
      </tr>

      {/* Expanded: nested ads table */}
      {isExpanded && (
        <tr>
          <td colSpan={9} className="bg-gray-50 px-6 py-4">
            {isLoadingAds ? (
              <LoadingSpinner className="py-4" size="sm" />
            ) : adsError ? (
              <div className="py-4 text-center text-sm text-red-600">{adsError}</div>
            ) : ads && ads.length === 0 ? (
              <div className="py-4 text-center text-sm text-gray-400">
                No ads found in this ad set
              </div>
            ) : ads ? (
              <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-6 py-2.5 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                        Ad Name
                      </th>
                      <th className="px-4 py-2.5 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                        Spend
                      </th>
                      <th className="px-4 py-2.5 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                        Impressions
                      </th>
                      <th className="px-4 py-2.5 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                        Clicks
                      </th>
                      <th className="px-4 py-2.5 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                        Leads
                      </th>
                      <th className="px-4 py-2.5 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                        CPC
                      </th>
                      <th className="px-4 py-2.5 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                        CPM
                      </th>
                      <th className="px-4 py-2.5 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                        CTR
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {ads.map((ad) => (
                      <tr key={ad.meta_ad_id} className="transition-colors hover:bg-gray-50">
                        <td className="whitespace-nowrap px-6 py-3 text-sm font-medium text-gray-900">
                          {ad.meta_ad_name || 'Unnamed Ad'}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-700">
                          {formatCurrency(ad.spend)}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-700">
                          {formatNumber(ad.impressions)}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-700">
                          {formatNumber(ad.clicks)}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-700">
                          {formatNumber(ad.leads)}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-700">
                          {fmtNullable(ad.cpc, formatCurrency)}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-700">
                          {fmtNullable(ad.cpm, formatCurrency)}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-700">
                          {fmtNullable(ad.ctr, (v) => formatPercent(v))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </td>
        </tr>
      )}
    </>
  );
}
