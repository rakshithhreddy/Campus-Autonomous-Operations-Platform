import React, { useState, useEffect } from "react";
import { Plug, XCircle, Link as LinkIcon, RefreshCcw, AlertTriangle, Info, ExternalLink } from "lucide-react";
import { apiUrl } from "../lib/apiBase";
import "./IntegrationsHub.css";

// OAuth setup instructions for common issues
const OAUTH_HELP = {
  google: {
    title: "Google OAuth Setup Required",
    steps: [
      "1. Go to Google Cloud Console → APIs & Services → OAuth consent screen",
      "2. Add your email as a test user (under 'Test users' section)",
      "3. Make sure the app is set to 'Testing' mode",
      "4. Try connecting again after adding your email"
    ],
    link: "https://console.cloud.google.com/apis/credentials/consent"
  },
  zoom: {
    title: "Zoom OAuth Setup Required",
    steps: [
      "1. Go to Zoom Marketplace → Develop → Build App",
      "2. Create or select your OAuth app",
      "3. Add redirect URL: http://localhost:8000/api/oauth/callback/zoom",
      "4. Copy Client ID and Secret to your .env file"
    ],
    link: "https://marketplace.zoom.us/develop/create"
  },
  github: {
    title: "GitHub OAuth Setup Required",
    steps: [
      "1. Go to GitHub Settings → Developer Settings → OAuth Apps",
      "2. Create new OAuth App or update existing",
      "3. Set callback URL: http://localhost:8000/api/oauth/callback",
      "4. Copy Client ID and Secret to your .env file"
    ],
    link: "https://github.com/settings/developers"
  }
};

export default function IntegrationsHub({ userId = "default" }) {
  const [connected, setConnected] = useState([]);
  const [available, setAvailable] = useState([]);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(null);
  const [notice, setNotice] = useState(null);
  const [showHelp, setShowHelp] = useState(null);

  const fetchIntegrations = async () => {
    setLoading(true);
    try {
      const res = await fetch(apiUrl(`/api/integrations/?user_id=${encodeURIComponent(userId)}`));
      if (res.ok) {
        const data = await res.json();
        setConnected(data.connected || []);
        setAvailable(data.available || []);
      }
    } catch (err) {
      console.error("Failed to fetch integrations:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIntegrations();
  }, [userId]);

  // Determine which OAuth help to show based on service
  const getHelpKey = (service) => {
    if (service.includes('google') || service.includes('gmail') || service.includes('calendar') || service.includes('drive')) {
      return 'google';
    }
    if (service.includes('zoom')) return 'zoom';
    if (service.includes('github')) return 'github';
    return null;
  };

  const handleConnect = async (service) => {
    setProcessing(service);
    setNotice(null);
    setShowHelp(null);
    try {
      const res = await fetch(apiUrl('/api/integrations/connect'), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, service })
      });
      if (res.ok) {
        const data = await res.json();
        const redirectUrl = data.oauth_url || data.auth_url || data.authorization_url;
        if (redirectUrl) {
          // Open OAuth in new window to preserve chat state
          const oauthWindow = window.open(redirectUrl, '_blank', 'width=600,height=700');

          // Show help info for potential OAuth issues
          const helpKey = getHelpKey(service);
          if (helpKey) {
            setNotice({
              type: "info",
              message: `Opening ${service} authorization. If you see "Access blocked" or errors, click "Help" below.`,
              helpKey
            });
          }

          // Poll to check if window closed (user completed OAuth)
          const checkClosed = setInterval(() => {
            if (oauthWindow && oauthWindow.closed) {
              clearInterval(checkClosed);
              // Refresh integrations after OAuth completes
              fetchIntegrations();
              setNotice(null);
            }
          }, 1000);
        } else {
          if (data?.status === "pending_setup") {
            const setupPath = data.setup_url || "/api/oauth/setup-guide";
            setNotice({
              type: "warning",
              message: data.message || "Integration requires OAuth setup before it can connect.",
              setupUrl: apiUrl(setupPath),
              helpKey: getHelpKey(service)
            });
          }
          await fetchIntegrations();
        }
      } else {
        const detail = await res.text().catch(() => "");
        const helpKey = getHelpKey(service);
        setNotice({
          type: "error",
          message: `Connect failed (${res.status}). ${detail}`.trim(),
          helpKey
        });
      }
    } catch (err) {
      console.error("Connect error:", err);
      setNotice({
        type: "error",
        message: "Connect error. Check backend is running and reachable.",
      });
    } finally {
      setProcessing(null);
    }
  };

  const handleRevoke = async (service) => {
    if (!window.confirm(`Are you sure you want to revoke access to ${service}?`)) return;
    setProcessing(service);
    try {
      const res = await fetch(apiUrl(`/api/integrations/service/${encodeURIComponent(service)}?user_id=${encodeURIComponent(userId)}`), {
        method: "DELETE",
      });
      if (res.ok) {
        await fetchIntegrations(); // Refresh list
      }
    } catch (err) {
      console.error("Revoke error:", err);
    } finally {
      setProcessing(null);
    }
  };

  return (
    <div className="integrations-hub" style={{
      width: '100%',
      padding: '16px',
      maxHeight: 'calc(100vh - 140px)',
      overflowY: 'auto',
      overflowX: 'hidden'
    }}>
      <h2 className="text-xl font-bold mb-4 flex items-center gap-2 text-white">
        <Plug className="w-5 h-5 text-blue-400" />
        Integrations Hub
      </h2>

      {/* OAuth Help Banner */}
      <div className="mb-4 rounded-lg border border-blue-500/30 bg-blue-500/10 p-3 text-sm">
        <div className="flex items-start gap-2">
          <Info className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
          <div className="text-gray-200">
            <strong className="text-blue-300">Note:</strong> Google OAuth apps in testing mode require your email to be added as a test user.
            If you see "Access blocked" errors, follow the setup instructions below.
          </div>
        </div>
      </div>

      {notice && (
        <div className={`mb-4 rounded-lg border p-3 text-sm ${
          notice.type === "error" ? "border-red-500/30 bg-red-500/10" :
          notice.type === "warning" ? "border-yellow-500/30 bg-yellow-500/10" :
          "border-blue-500/30 bg-blue-500/10"
        }`}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-start gap-2">
                {notice.type === "error" ? (
                  <XCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
                ) : notice.type === "warning" ? (
                  <AlertTriangle className="w-5 h-5 text-yellow-400 flex-shrink-0" />
                ) : (
                  <Info className="w-5 h-5 text-blue-400 flex-shrink-0" />
                )}
                <div className={
                  notice.type === "error" ? "text-red-300" :
                  notice.type === "warning" ? "text-yellow-300" :
                  "text-gray-200"
                }>
                  {notice.message}
                </div>
              </div>

              <div className="flex gap-3 mt-2 ml-7">
                {notice.setupUrl && (
                  <a
                    href={notice.setupUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-blue-300 hover:text-blue-200 underline"
                  >
                    Setup Guide <ExternalLink className="w-3 h-3" />
                  </a>
                )}
                {notice.helpKey && OAUTH_HELP[notice.helpKey] && (
                  <button
                    onClick={() => setShowHelp(showHelp === notice.helpKey ? null : notice.helpKey)}
                    className="inline-flex items-center gap-1 text-purple-300 hover:text-purple-200"
                  >
                    {showHelp === notice.helpKey ? "Hide Help" : "Show Help"}
                  </button>
                )}
              </div>
            </div>
            <button
              onClick={() => { setNotice(null); setShowHelp(null); }}
              className="shrink-0 text-gray-400 hover:text-gray-200"
              aria-label="Dismiss"
              title="Dismiss"
            >
              <XCircle className="w-5 h-5" />
            </button>
          </div>
        </div>
      )}

      {/* Expandable OAuth Help Section */}
      {showHelp && OAUTH_HELP[showHelp] && (
        <div className="mb-4 rounded-lg border border-purple-500/30 bg-purple-500/10 p-4 text-sm">
          <h4 className="font-bold text-purple-300 mb-3">{OAUTH_HELP[showHelp].title}</h4>
          <ul className="space-y-2 text-gray-300 mb-3">
            {OAUTH_HELP[showHelp].steps.map((step, i) => (
              <li key={i}>{step}</li>
            ))}
          </ul>
          <a
            href={OAUTH_HELP[showHelp].link}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 px-3 py-1.5 bg-purple-500/20 rounded-md text-purple-300 hover:bg-purple-500/30 transition"
          >
            Open Settings <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      )}

      {loading ? (
        <div className="integration-loader">
          <RefreshCcw className="w-8 h-8 animate-spin text-gray-400" />
        </div>
      ) : (
        <>
          <section className="integrations-section mb-10">
            <h3 className="text-xl font-semibold mb-4 text-gray-300 border-b border-white/10 pb-2">Connected Apps</h3>
            {connected.length === 0 ? (
              <div className="empty-state">No integrations connected yet.</div>
            ) : (
              <div className="integration-grid grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {connected.map((app) => (
                  <div key={app.service} className="integration-card bg-gray-800/80 p-4 rounded-lg border border-gray-700 hover:border-gray-600 transition flex flex-col">
                    <div className="integration-header flex items-center gap-3 mb-2">
                      <span className="text-3xl">{app.icon || "🔗"}</span>
                      <div>
                        <h4 className="font-bold text-gray-100 m-0">{app.name || app.service}</h4>
                        <span className="integration-status connected text-xs px-2 py-0.5 rounded-full bg-green-500/20 text-green-400">Connected</span>
                      </div>
                    </div>
                    <div className="text-sm text-gray-400 mb-4 flex-1">
                      Connected on {new Date(app.connected_at).toLocaleDateString()}
                    </div>
                    <div className="integration-actions flex justify-end">
                      <button
                        onClick={() => handleRevoke(app.service)}
                        disabled={processing === app.service}
                        className="btn-revoke px-3 py-1.5 rounded-md bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition disabled:opacity-50 text-sm"
                      >
                        {processing === app.service ? "Revoking..." : "Revoke Access"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="integrations-section">
            <h3 className="text-xl font-semibold mb-4 text-gray-300 border-b border-white/10 pb-2">Available Integrations</h3>
            {available.length === 0 ? (
              <div className="empty-state">All available apps are connected!</div>
            ) : (
              <div className="integration-grid grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {available.map((app) => (
                  <div key={app.service} className="integration-card bg-gray-800/50 p-4 rounded-lg border border-gray-700/50 hover:border-gray-600 transition flex flex-col">
                    <div className="integration-header flex items-center gap-3 mb-2">
                      <span className="text-3xl">{app.icon || "🔗"}</span>
                      <div>
                        <h4 className="font-bold text-gray-200 m-0">{app.name || app.service}</h4>
                        <span className="integration-status available text-xs px-2 py-0.5 rounded-full bg-gray-500/20 text-gray-400">Not Connected</span>
                      </div>
                    </div>
                    <div className="integration-desc text-sm text-gray-400 mb-4 flex-1">
                      {app.description}
                    </div>
                    <div className="integration-actions flex justify-between items-center">
                      <button
                        onClick={() => setShowHelp(getHelpKey(app.service))}
                        className="text-xs text-gray-500 hover:text-gray-300"
                      >
                        Setup help?
                      </button>
                      <button
                        onClick={() => handleConnect(app.service)}
                        disabled={processing === app.service}
                        className="btn-connect px-3 py-1.5 rounded-md bg-blue-500 text-white font-medium hover:bg-blue-600 shadow-lg shadow-blue-500/20 transition disabled:opacity-50 flex items-center gap-1 text-sm"
                      >
                        <LinkIcon className="w-4 h-4" />
                        {processing === app.service ? "Connecting..." : "Connect"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}