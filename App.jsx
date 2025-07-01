import React, { useState, useEffect } from "react";
import mqtt from "mqtt";

const defaultParams = [
  { name: "speed", type: "number", min: 0, max: 120, interval: 3, enabled: true },
  { name: "fuel_level", type: "number", min: 10, max: 100, interval: 5, enabled: true },
  { name: "engine_temp", type: "number", min: 60, max: 110, interval: 5, enabled: true },
  { name: "latitude", type: "number", min: 12.8341, max: 13.1414, interval: 10, enabled: true },
  { name: "longitude", type: "number", min: 77.4489, max: 77.7845, interval: 10, enabled: true },
  { name: "engine_rpm", type: "number", min: 800, max: 3500, interval: 3, enabled: true },
  { name: "battery_voltage", type: "number", min: 11.5, max: 14.4, interval: 10, enabled: true },
  { name: "odometer", type: "number", min: 50000, max: 500000, interval: 30, enabled: true },
  { name: "engine_status", type: "string", length: 8, interval: 5, enabled: true },
  { name: "brake_status", type: "string", length: 8, interval: 5, enabled: true },
  { name: "door_status", type: "string", length: 8, interval: 5, enabled: true },
  { name: "air_pressure", type: "number", min: 80, max: 120, interval: 10, enabled: true }
];

const App = () => {
  const [params, setParams] = useState([...defaultParams]);
  const [client, setClient] = useState(null);
  const [data, setData] = useState([]);
  const [connected, setConnected] = useState(false);
  const [streaming, setStreaming] = useState(false);

  useEffect(() => {
    const mqttClient = mqtt.connect("wss://test.mosquitto.org:8081");
    mqttClient.on("connect", () => {
      setConnected(true);
      mqttClient.subscribe("truck/sensor/data");
    });
    mqttClient.on("disconnect", () => setConnected(false));
    mqttClient.on("error", () => setConnected(false));
    mqttClient.on("message", (topic, message) => {
      if (!streaming) return;
      try {
        const newData = JSON.parse(message.toString());
        setData(prev => [...prev.slice(-49), newData]);
      } catch (e) {}
    });
    setClient(mqttClient);
    return () => mqttClient.end();
  }, [streaming]);

  function addParam() {
    setParams(prev => [...prev, { name: "", type: "number", min: 0, max: 100, interval: 5, enabled: true }]);
  }
  function removeParam(idx) {
    setParams(prev => prev.filter((_, i) => i !== idx));
  }
  function updateParam(idx, field, value) {
    setParams(prev => prev.map((p, i) => i === idx ? { ...p, [field]: value } : p));
  }

  function sendConfig() {
    if (!client || !connected) return;
    const configPayload = {};
    params.forEach(p => {
      if (!p.enabled || !p.name.trim()) return;
      configPayload[p.name] = { type: p.type, interval: Number(p.interval) };
      if (p.type === "number") {
        configPayload[p.name].min = Number(p.min);
        configPayload[p.name].max = Number(p.max);
      }
      if (p.type === "string") {
        configPayload[p.name].length = Number(p.length) || 10;
      }
    });
    client.publish("truck/control/config", JSON.stringify(configPayload));
  }

  function startStream() {
    setData([]);
    setStreaming(true);
    sendConfig();
  }
  function stopStream() { setStreaming(false); }

  return (
    <div className="dashboard-container">
      <div className="header">
        <h1>DICV Telemetry Dashboard</h1>
        <div className="status-indicator">
          <div className={`status-dot ${connected ? 'status-connected' : 'status-disconnected'}`}></div>
          <span>{connected ? "Connected" : "Disconnected"}</span>
        </div>
      </div>
      <div className="main-content">
        <div className="config-panel">
          <h3>Parameters</h3>
          {params.map((p, idx) => (
            <div key={idx} className="param-row">
              <input type="checkbox" checked={p.enabled} onChange={e => updateParam(idx, "enabled", e.target.checked)} />
              <input type="text" value={p.name} placeholder="Parameter name" onChange={e => updateParam(idx, "name", e.target.value)} style={{ width: 120 }} />
              <select value={p.type} onChange={e => updateParam(idx, "type", e.target.value)} style={{ width: 90 }}>
                <option value="number">Number</option>
                <option value="string">String</option>
              </select>
              {p.type === "number" && (
                <>
                  <input type="number" value={p.min} style={{ width: 60 }} onChange={e => updateParam(idx, "min", e.target.value)} />
                  <span>to</span>
                  <input type="number" value={p.max} style={{ width: 60 }} onChange={e => updateParam(idx, "max", e.target.value)} />
                </>
              )}
              {p.type === "string" && (
                <>
                  <span>len</span>
                  <input type="number" value={p.length || 10} style={{ width: 60 }} min={1} max={100} onChange={e => updateParam(idx, "length", e.target.value)} />
                </>
              )}
              <span>Interval</span>
              <input type="number" value={p.interval} style={{ width: 60 }} min={0.1} max={60} step={0.1} onChange={e => updateParam(idx, "interval", e.target.value)} />
              <button className="remove-btn" onClick={() => removeParam(idx)} title="Remove parameter">✖</button>
            </div>
          ))}
          <button onClick={addParam} style={{ margin: "10px 0", background: "#6366f1", color: "#fff", border: "none", borderRadius: 6, padding: "8px 14px", fontWeight: "bold", cursor: "pointer" }}>+ Add Parameter</button>
          <div className="control-buttons">
            <button className="btn btn-start" onClick={startStream} disabled={!connected}>▶️ Start Stream</button>
            <button className="btn btn-stop" onClick={stopStream}>⏹️ Stop Stream</button>
          </div>
        </div>
        {/* ...data panel as before... */}
      </div>
    </div>
  );
};

export default App;
