export default function Settings() {
  return (
    <div className="p-6 space-y-5">
      <h2 className="text-lg font-semibold text-white">Settings</h2>

      <div className="bg-surface-card border border-surface-border rounded-xl p-5 space-y-4 max-w-lg">
        <h3 className="text-sm font-medium text-gray-400">Danger Zone</h3>

        <div className="border border-accent-red/30 rounded-lg p-4 space-y-3">
          <div>
            <p className="text-sm text-white font-medium">Reset Paper Portfolio</p>
            <p className="text-xs text-gray-500 mt-0.5">
              Wipes all positions, signals, and portfolio history. Resets balance to starting
              amount. This cannot be undone.
            </p>
          </div>
          <button
            className="px-4 py-2 bg-accent-red/20 text-accent-red border border-accent-red/30 rounded-lg text-sm hover:bg-accent-red/30 transition-colors"
            onClick={() => {
              if (confirm("Reset paper portfolio? This cannot be undone.")) {
                fetch("/api/portfolio/reset", { method: "POST" })
                  .then(() => window.location.reload())
                  .catch(console.error);
              }
            }}
          >
            Reset Portfolio
          </button>
        </div>
      </div>

      <div className="bg-surface-card border border-surface-border rounded-xl p-5 max-w-lg">
        <h3 className="text-sm font-medium text-gray-400 mb-3">System Info</h3>
        <div className="space-y-2 text-xs font-mono">
          <div className="flex justify-between text-gray-500">
            <span>Dashboard</span>
            <span className="text-white">Okane v0.1.0</span>
          </div>
          <div className="flex justify-between text-gray-500">
            <span>Grafana Monitoring</span>
            <a href={`${window.location.protocol}//${window.location.hostname}:7824`} target="_blank" rel="noreferrer" className="text-accent-blue hover:underline">
              Open →
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
