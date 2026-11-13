import { useEffect, useState } from 'react'
import { Brain, Copy, Gauge, Ruler, Target } from '@phosphor-icons/react'
import { api, label } from '../api'
import { CLASS_HEX, RISK_HEX, Tile } from '../icons'

const pct = (v: number) => `${Math.round(v * 100)}`

function Ring({ value, color, size = 64 }: { value: number; color: string; size?: number }) {
  const r = size / 2 - 5
  const c = 2 * Math.PI * r
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--fill-2)" strokeWidth="6" />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="6" strokeLinecap="round"
        strokeDasharray={`${c * value} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
    </svg>
  )
}

const RISK_PARTS = [
  { k: 'Severity of the damage', w: 45, c: '#ff3b30', d: 'Measured from the image: size, depth and roughness.' },
  { k: 'Type of damage', w: 20, c: '#ff9500', d: 'Potholes count most, then alligator, transverse and longitudinal cracks.' },
  { k: 'Road and traffic', w: 20, c: '#007aff', d: 'Highways and busy roads rank higher. Unknown roads count as average.' },
  { k: 'Position in the lane', w: 15, c: '#5856d6', d: 'Damage in the wheel path is riskier than at the road edge.' },
]

export default function Model() {
  const [m, setM] = useState<any>(null)
  const [health, setHealth] = useState<any>(null)
  useEffect(() => {
    api.metrics().then(setM)
    api.health().then(setHealth)
  }, [])
  const models = health?.model?.models ?? []

  return (
    <>
      <div className="page-h">
        <div>
          <h1>AI model</h1>
          <p>How detection, severity, risk and duplicate matching work, and how accurate they are on images the model never saw.</p>
        </div>
      </div>

      <div className="grid g-wide">
        <div className="card">
          <div className="row" style={{ marginBottom: 14 }}>
            <Tile icon={Target} color="#34c759" size={30} />
            <h3 style={{ margin: 0 }}>Detection accuracy</h3>
          </div>
          {!m?.available ? (
            <div className="empty">No evaluation yet. Run the evaluation script to fill this in.</div>
          ) : (
            <div className="acc-grid">
              {m.per_class.map((c: any) => (
                <div key={c.class} className="acc">
                  <div className="acc-ring">
                    <Ring value={c.map50} color={CLASS_HEX[c.class] ?? '#8e8e93'} />
                    <b>{pct(c.map50)}</b>
                  </div>
                  <div>
                    <div className="acc-name">{label(c.class)}</div>
                    <div className="note">mAP at 50% overlap</div>
                    <div className="acc-sub">
                      <span>Precision <b>{pct(c.precision)}%</b></span>
                      <span>Recall <b>{pct(c.recall)}%</b></span>
                      <span>F1 <b>{pct(c.f1)}%</b></span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
          {m?.sources && (
            <p className="note" style={{ marginTop: 14 }}>
              Cracks: {m.sources.cracks}. Potholes: {m.sources.pothole}. The public RDD2022 model this replaced scored {pct(m.sources.baseline_pothole_map50)}% on the same pothole test.
            </p>
          )}
        </div>

        <div className="card">
          <div className="row" style={{ marginBottom: 14 }}>
            <Tile icon={Brain} color="#ff2d55" size={30} />
            <h3 style={{ margin: 0 }}>Models in use</h3>
          </div>
          {models.map((x: any) => (
            <div key={x.role} className="model-row">
              <div>
                <b>{x.role === 'pothole' ? 'Pothole specialist' : 'Crack detector'}</b>
                <div className="note">{x.weights}</div>
              </div>
              <div className="row" style={{ gap: 4 }}>
                {x.classes.map((c: string) => <span key={c} className="pill" style={{ color: CLASS_HEX[c], background: `${CLASS_HEX[c]}22` }}>{label(c)}</span>)}
              </div>
            </div>
          ))}
          <div className="model-row">
            <div><b>Tracking</b><div className="note">ByteTrack, a defect needs 3 frames before it gets an ID</div></div>
          </div>
          <div className="model-row">
            <div><b>Hardware</b><div className="note">{health?.cuda ? 'NVIDIA GPU, half precision' : 'CPU'}</div></div>
          </div>
        </div>
      </div>

      <div className="grid g3" style={{ marginTop: 16 }}>
        <div className="card">
          <div className="row" style={{ marginBottom: 14 }}>
            <Tile icon={Gauge} color="#ff3b30" size={30} />
            <h3 style={{ margin: 0 }}>Risk score</h3>
          </div>
          <div className="stack-bar">
            {RISK_PARTS.map((p) => <div key={p.k} style={{ flex: p.w, background: p.c }} title={`${p.k} ${p.w}%`} />)}
          </div>
          {RISK_PARTS.map((p) => (
            <div key={p.k} className="weight">
              <i style={{ background: p.c }} />
              <div><b>{p.k}</b> <span className="muted">{p.w} points</span><div className="note">{p.d}</div></div>
            </div>
          ))}
          <div className="weight">
            <i style={{ background: '#8e8e93' }} />
            <div><b>Extra points</b><div className="note">Up to 12 for repeat citizen reports, 8 when it is getting worse.</div></div>
          </div>
          <div className="bands">
            <span style={{ background: `${RISK_HEX.Low}26`, color: RISK_HEX.Low }}>Low under 40</span>
            <span style={{ background: `${RISK_HEX.Medium}26`, color: RISK_HEX.Medium }}>Medium 40 to 69</span>
            <span style={{ background: `${RISK_HEX.High}26`, color: RISK_HEX.High }}>High 70 and up</span>
          </div>
        </div>

        <div className="card">
          <div className="row" style={{ marginBottom: 14 }}>
            <Tile icon={Ruler} color="#ff9500" size={30} />
            <h3 style={{ margin: 0 }}>Severity</h3>
          </div>
          <p className="note" style={{ marginTop: 0 }}>The damaged area inside each box is traced with OpenCV, then measured three ways.</p>
          <div className="weight"><i style={{ background: '#ff3b30' }} /><div><b>Size</b><div className="note">Traced area, corrected for distance so far-away potholes are not undercounted.</div></div></div>
          <div className="weight"><i style={{ background: '#5856d6' }} /><div><b>Depth</b><div className="note">How much darker or wetter the hole is than the road around it.</div></div></div>
          <div className="weight"><i style={{ background: '#30b0c7' }} /><div><b>Roughness</b><div className="note">Broken, jagged edges inside the damaged area.</div></div></div>
          <p className="note">Calibrated on 2,400 real potholes: 40% rate low, 40% medium, 20% high.</p>
        </div>

        <div className="card">
          <div className="row" style={{ marginBottom: 14 }}>
            <Tile icon={Copy} color="#5856d6" size={30} />
            <h3 style={{ margin: 0 }}>Duplicate reports</h3>
          </div>
          <p className="note" style={{ marginTop: 0 }}>A new sighting joins an existing defect instead of creating a second record when both are true:</p>
          <div className="weight"><i style={{ background: '#007aff' }} /><div><b>Within 15 metres</b><div className="note">30 metres when the location was pinned by hand.</div></div></div>
          <div className="weight"><i style={{ background: '#34c759' }} /><div><b>Looks like the same damage</b><div className="note">Image similarity from a DINOv2 vision model. Without GPS the match must be much closer.</div></div></div>
          <p className="note">The same photo uploaded twice is caught separately by an image fingerprint.</p>
        </div>
      </div>
    </>
  )
}
