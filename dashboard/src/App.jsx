import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, AlertTriangle, Gauge, HeartPulse, LayoutDashboard, Map, RefreshCcw, ShoppingBag, Users } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import './styles.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const STORE_ID = import.meta.env.VITE_STORE_ID || 'ST1008';

function App() {
  const [page, setPage] = useState('dashboard');
  const [metrics, setMetrics] = useState(null);
  const [funnel, setFunnel] = useState(null);
  const [heatmap, setHeatmap] = useState(null);
  const [anomalies, setAnomalies] = useState([]);
  const [health, setHealth] = useState(null);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const [m, f, h, a, status] = await Promise.all([
        fetch(`${API}/stores/${STORE_ID}/metrics`).then(r => r.json()),
        fetch(`${API}/stores/${STORE_ID}/funnel`).then(r => r.json()),
        fetch(`${API}/stores/${STORE_ID}/heatmap`).then(r => r.json()),
        fetch(`${API}/stores/${STORE_ID}/anomalies`).then(r => r.json()),
        fetch(`${API}/health`).then(r => r.json())
      ]);
      setMetrics(m);
      setFunnel(f);
      setHeatmap(h);
      setAnomalies(a);
      setHealth(status);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    const wsUrl = API.replace('http://', 'ws://').replace('https://', 'wss://') + '/ws';
    const ws = new WebSocket(wsUrl);
    ws.onmessage = (message) => {
      const payload = JSON.parse(message.data);
      setEvents(previous => [payload.event, ...previous].slice(0, 8));
      refresh();
    };
    return () => ws.close();
  }, []);

  const nav = [
    ['dashboard', LayoutDashboard],
    ['funnel', ShoppingBag],
    ['heatmap', Map],
    ['anomalies', AlertTriangle],
    ['health', HeartPulse]
  ];

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><Gauge size={22} /> Store Intel</div>
        <nav>
          {nav.map(([key, Icon]) => (
            <button key={key} className={page === key ? 'active' : ''} onClick={() => setPage(key)} title={key}>
              <Icon size={18} /><span>{title(key)}</span>
            </button>
          ))}
        </nav>
      </aside>
      <main>
        <header>
          <div>
            <p className="eyebrow">{STORE_ID}</p>
            <h1>{title(page)}</h1>
          </div>
          <button className="iconButton" onClick={refresh} title="Refresh data">
            <RefreshCcw size={18} className={loading ? 'spin' : ''} />
          </button>
        </header>
        {page === 'dashboard' && <Dashboard metrics={metrics} anomalies={anomalies} events={events} />}
        {page === 'funnel' && <Funnel funnel={funnel} />}
        {page === 'heatmap' && <Heatmap heatmap={heatmap} />}
        {page === 'anomalies' && <Anomalies anomalies={anomalies} />}
        {page === 'health' && <Health health={health} />}
      </main>
    </div>
  );
}

function Dashboard({ metrics, anomalies, events }) {
  const cards = [
    ['Visitors', metrics?.unique_visitors ?? 0, Users],
    ['Conversion', pct(metrics?.conversion_rate), ShoppingBag],
    ['Queue Depth', metrics?.queue_depth ?? 0, Activity],
    ['Abandonment', pct(metrics?.abandonment_rate), AlertTriangle]
  ];
  return (
    <>
      <section className="kpis">
        {cards.map(([label, value, Icon]) => (
          <article className="card" key={label}>
            <Icon size={18} />
            <span>{label}</span>
            <strong>{value}</strong>
          </article>
        ))}
      </section>
      <section className="twoCol">
        <div className="panel">
          <h2>Live Events</h2>
          <div className="eventList">
            {events.length === 0 ? <p className="muted">Waiting for camera events.</p> : events.map(event => (
              <div className="eventRow" key={event.event_id}>
                <span>{event.event_type}</span>
                <strong>{event.visitor_id}</strong>
                <small>{event.zone_id || event.camera_id}</small>
              </div>
            ))}
          </div>
        </div>
        <div className="panel">
          <h2>Active Anomalies</h2>
          {anomalies.length === 0 ? <p className="muted">No active anomalies.</p> : anomalies.map(item => (
            <div className="alert" key={`${item.anomaly_type}-${item.detected_at}`}>
              <strong>{item.anomaly_type}</strong>
              <span>{item.description}</span>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}

function Funnel({ funnel }) {
  const data = useMemo(() => [
    { stage: 'Entry', value: funnel?.entered ?? 0 },
    { stage: 'Zone', value: funnel?.zone_visit ?? 0 },
    { stage: 'Billing', value: funnel?.billing ?? 0 },
    { stage: 'Purchase', value: funnel?.purchase ?? 0 }
  ], [funnel]);
  return <ChartPanel data={data} dataKey="value" />;
}

function Heatmap({ heatmap }) {
  const data = heatmap?.zones ?? [];
  return (
    <section className="panel tall">
      <h2>Zone Performance</h2>
      <ResponsiveContainer width="100%" height={360}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="zone_id" />
          <YAxis />
          <Tooltip />
          <Bar dataKey="visits" fill="#2764d8" radius={[4, 4, 0, 0]} />
          <Bar dataKey="average_dwell_ms" fill="#22a06b" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}

function Anomalies({ anomalies }) {
  return (
    <section className="panel tall">
      <h2>Anomaly Workbench</h2>
      {anomalies.length === 0 ? <p className="muted">No active anomalies.</p> : anomalies.map(item => (
        <article className="anomaly" key={`${item.anomaly_type}-${item.detected_at}`}>
          <div><strong>{item.anomaly_type}</strong><span className={`severity ${item.severity}`}>{item.severity}</span></div>
          <p>{item.description}</p>
          <small>{item.suggested_action}</small>
        </article>
      ))}
    </section>
  );
}

function Health({ health }) {
  return (
    <section className="panel tall">
      <h2>System Health</h2>
      <div className="healthGrid">
        <Status label="API" value={health?.status || 'unknown'} />
        <Status label="Database" value={health?.database || 'unknown'} />
        <Status label="Stale Feed" value={health?.stale_feed_warning ? 'warning' : 'clear'} />
        <Status label="Last Event" value={health?.last_event_timestamp || 'none'} />
      </div>
    </section>
  );
}

function ChartPanel({ data }) {
  return (
    <section className="panel tall">
      <h2>Session Funnel</h2>
      <ResponsiveContainer width="100%" height={360}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="stage" />
          <YAxis allowDecimals={false} />
          <Tooltip />
          <Line type="monotone" dataKey="value" stroke="#2764d8" strokeWidth={3} dot={{ r: 5 }} />
        </LineChart>
      </ResponsiveContainer>
    </section>
  );
}

function Status({ label, value }) {
  return <div className="status"><span>{label}</span><strong>{value}</strong></div>;
}

function pct(value) {
  return `${Math.round((value || 0) * 100)}%`;
}

function title(value) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

createRoot(document.getElementById('root')).render(<App />);
