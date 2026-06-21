'use client'

import { useState, useEffect } from 'react'
import { motion, type Variants } from 'framer-motion'
import { ArrowRight, Check, ScanLine } from 'lucide-react'
import './hero.css'

// ─── Animation variants ───────────────────────────────────────
const fadeUp: Variants = {
  hidden: { opacity: 0, y: 40 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: 'easeOut' } },
}
const stagger: Variants = { hidden: {}, visible: { transition: { staggerChildren: 0.1 } } }

const GOLD = 'linear-gradient(135deg, #f0b90b 0%, #fcd535 100%)'

function useWindowWidth(): number {
  const [w, setW] = useState(1200)
  useEffect(() => {
    setW(window.innerWidth)
    const fn = () => setW(window.innerWidth)
    window.addEventListener('resize', fn)
    return () => window.removeEventListener('resize', fn)
  }, [])
  return w
}

// ─── Shared util components ────────────────────────────────────
function GradBtn({ href, children, className = '' }: { href: string; children: React.ReactNode; className?: string }) {
  return (
    <motion.div whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.98 }} style={{ display: 'inline-flex' }}>
      <a href={href} className={`btn-gradient ${className}`} style={{
        display: 'inline-flex', alignItems: 'center', gap: 8,
        borderRadius: 8, padding: '14px 30px', fontSize: 15,
        fontWeight: 800, textDecoration: 'none', color: '#0b0e11',
      }}>
        {children}
      </a>
    </motion.div>
  )
}

function GhostBtn({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <motion.div whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.98 }} style={{ display: 'inline-flex' }}>
      <a href={href} className="btn-ghost" style={{
        display: 'inline-flex', alignItems: 'center', gap: 8,
        borderRadius: 8, padding: '14px 30px', fontSize: 15,
        fontWeight: 700, textDecoration: 'none', color: '#eaecef',
      }}>
        {children}
      </a>
    </motion.div>
  )
}

// label/value stat block, mirroring the banner's "TOTAL PRIZE POOL / $36,000"
function StatBlock({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, letterSpacing: '0.16em', textTransform: 'uppercase', color: '#f0b90b', marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 900, color: '#eaecef', letterSpacing: '-0.02em', lineHeight: 1 }}>{value}</div>
    </div>
  )
}

// ─── Floating EDI signal card (dark, gold) ────────────────────
function SignalCard() {
  const conditions = [
    'F&G extreme · 3-day streak',
    'Funding rate contradiction',
    'Momentum exhaustion',
  ]
  return (
    <motion.div
      animate={{ y: [-8, 8, -8], rotate: [0, 1, -1, 0] }}
      transition={{ repeat: Infinity, duration: 6, ease: 'easeInOut' }}
      style={{
        width: 320, background: '#181a20', borderRadius: 18,
        border: '1px solid rgba(240,185,11,0.22)',
        boxShadow: '0 40px 100px -20px rgba(240,185,11,0.25), 0 0 0 1px rgba(0,0,0,0.4)',
        padding: 26, display: 'flex', flexDirection: 'column', gap: 16,
        position: 'relative', zIndex: 10,
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ width: 36, height: 36, borderRadius: 9, background: GOLD, display: 'grid', placeItems: 'center' }}>
          <ScanLine size={18} color="#0b0e11" />
        </div>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase',
          padding: '3px 10px', borderRadius: 6, background: 'rgba(240,185,11,0.12)', color: '#f0b90b',
        }}>BTC · 1D</div>
      </div>

      {/* Confidence */}
      <div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#848e9c', marginBottom: 4, fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase' }}>Signal Confidence</div>
        <div style={{ fontSize: 44, fontWeight: 900, color: '#eaecef', letterSpacing: '-0.04em', lineHeight: 1 }}>0.90</div>
        <div style={{ fontSize: 12, color: '#f0b90b', marginTop: 6, fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          <ArrowRight size={13} style={{ transform: 'rotate(-45deg)' }} /> Bullish Reversal
        </div>
      </div>

      {/* Conditions checklist */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 9, borderTop: '1px solid #2b3139', paddingTop: 14 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#848e9c', fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase' }}>Conditions Met</div>
        {conditions.map((c) => (
          <div key={c} style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <span style={{ width: 16, height: 16, borderRadius: '50%', background: '#0ecb81', display: 'grid', placeItems: 'center', flexShrink: 0 }}>
              <Check size={11} color="#0b0e11" strokeWidth={3} />
            </span>
            <span style={{ fontSize: 12, color: '#eaecef', fontWeight: 600 }}>{c}</span>
          </div>
        ))}
      </div>

      {/* Risk details */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, borderTop: '1px solid #2b3139', paddingTop: 14 }}>
        {[
          ['Win Rate · ETH', '66.7%'],
          ['Risk / Trade', '2%'],
          ['Stop / Target', '3% / 5%'],
        ].map(([k, v]) => (
          <div key={k} style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ fontSize: 11, color: '#848e9c', fontWeight: 600 }}>{k}</span>
            <span style={{ fontSize: 11, color: '#eaecef', fontWeight: 700 }}>{v}</span>
          </div>
        ))}
      </div>

      {/* Export button */}
      <div style={{
        height: 44, background: GOLD,
        borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
        color: '#0b0e11', fontWeight: 800, fontSize: 14,
      }}>
        Export Evidence Pack →
      </div>
    </motion.div>
  )
}

// ─── Inline nav header ────────────────────────────────────────
function EdiNav() {
  return (
    <header className="edi-nav">
      <a href="#platform" className="edi-logo">
        <span className="edi-logo-tile"><span style={{ color: '#0b0e11', fontWeight: 900, fontSize: 15, lineHeight: 1 }}>◆</span></span>
        Emotional Duality
        <span className="edi-logo-badge">EDI v2</span>
      </a>
      <nav className="edi-nav-links">
        <a href="#how-it-works" className="edi-nav-link">HOW IT WORKS</a>
        <a href="#dashboard" className="edi-nav-link">DUALITY MAP</a>
        <a href="#ecosystem" className="edi-nav-link">EVIDENCE PACK</a>
        <a href="https://github.com/leobergjackson/BNB-hacakthon-2026" target="_blank" rel="noreferrer" className="edi-nav-link">DOCS</a>
      </nav>
      <a href="#dashboard" className="edi-nav-cta">View Duality Map</a>
    </header>
  )
}

// ─── MAIN HERO SECTION ────────────────────────────────────────
export default function HeroSection() {
  const w = useWindowWidth()
  const isMobile = w < 768

  return (
    <section className="hero-bg grain" id="platform" style={{ position: 'relative', overflow: 'hidden', background: '#0b0e11' }}>
      {/* Banner globe — right side background */}
      <div aria-hidden style={{
        position: 'absolute', top: 0, right: 0, bottom: 0, width: isMobile ? '100%' : '64%', zIndex: 0,
        backgroundImage: 'url(/bnb-banner.png)',
        backgroundSize: 'cover', backgroundPosition: 'right center', backgroundRepeat: 'no-repeat',
        opacity: isMobile ? 0.22 : 0.92, pointerEvents: 'none',
      }} />
      {/* Left fade over the globe to hide the baked-in banner text and blend to black */}
      <div aria-hidden style={{
        position: 'absolute', inset: 0, zIndex: 1, pointerEvents: 'none',
        background: 'linear-gradient(90deg, #0b0e11 0%, #0b0e11 46%, rgba(11,14,17,0.85) 60%, rgba(11,14,17,0.3) 80%, rgba(11,14,17,0.66) 100%)',
      }} />
      {/* Top fade so any residual banner text above the globe stays hidden */}
      <div aria-hidden style={{
        position: 'absolute', inset: 0, zIndex: 1, pointerEvents: 'none',
        background: 'linear-gradient(180deg, rgba(11,14,17,0.55) 0%, rgba(11,14,17,0) 22%, rgba(11,14,17,0) 80%, rgba(11,14,17,0.5) 100%)',
      }} />
      {/* Top hairline */}
      <div style={{ position: 'absolute', inset: '0 0 auto', height: 1, background: 'rgba(240,185,11,0.25)', zIndex: 2 }} />

      <div style={{ position: 'relative', zIndex: 10 }}>
        <EdiNav />
      </div>

      <div style={{
        maxWidth: 1280, margin: '0 auto',
        padding: isMobile ? '36px 20px 80px' : '52px 24px 120px',
        display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1.1fr 1fr',
        gap: isMobile ? 48 : 64, alignItems: 'center',
        position: 'relative', zIndex: 10,
      }}>
        {/* Left */}
        <motion.div variants={stagger} initial="hidden" animate="visible" style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 26 }}>
          <motion.div variants={fadeUp} style={{
            fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700, letterSpacing: '0.2em', textTransform: 'uppercase',
            color: '#f0b90b', display: 'inline-flex', alignItems: 'center', gap: 10,
          }}>
            <span style={{ width: 26, height: 1, background: '#f0b90b', display: 'inline-block' }} />
             CMC Skills Marketplace
          </motion.div>

          {/* Pixel headline — banner style */}
          <motion.h1 variants={fadeUp} style={{
            fontFamily: 'var(--font-pixel)', fontSize: 'clamp(26px, 5vw, 52px)', lineHeight: 1.32,
            color: '#eaecef', margin: 0, letterSpacing: '0.01em', textShadow: '0 3px 0 rgba(0,0,0,0.5)',
          }}>
            <span style={{ display: 'block' }}>VANTAGE</span>
            <span style={{ display: 'block', color: '#f0b90b' }}></span>
          </motion.h1>

          {/* Mono subtitle — like "AI TRADING AGENT EDITION" */}
          <motion.p variants={fadeUp} style={{
            fontFamily: 'var(--font-mono)', fontSize: 'clamp(13px, 1.7vw, 19px)', fontWeight: 700,
            letterSpacing: '0.16em', textTransform: 'uppercase', color: '#eaecef', margin: '-6px 0 0',
          }}>
            <span style={{ color: '#f0b90b' }}>&gt;</span> Trade the contradiction
          </motion.p>

          <motion.p variants={fadeUp} style={{ fontSize: 17, lineHeight: 1.65, color: '#848e9c', maxWidth: 520, margin: 0 }}>
            Single-axis sentiment just confirms the crowd. EDI v2 fires only when sustained retail Fear &amp; Greed extremes are violently contradicted by derivatives positioning and stalling momentum — the cognitive dissonance that precedes major reversals.
          </motion.p>

          {/* Banner-style stat row */}
          <motion.div variants={fadeUp} style={{ display: 'flex', gap: 48, flexWrap: 'wrap' }}>
            <StatBlock label="Signals / Year" value="~5" />
            <StatBlock label="Win Rate · ETH" value="66.7%" />
            <StatBlock label="Backtest" value="365d" />
          </motion.div>

          <motion.div variants={fadeUp} style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
            <GradBtn href="#dashboard">Explore the Duality Map <ArrowRight size={17} strokeWidth={2.4} /></GradBtn>
            <GhostBtn href="#how-it-works">See How It Works</GhostBtn>
          </motion.div>

          {/* Partners + badges row — like the banner's PARTNERS line */}
          <motion.div variants={fadeUp} style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center', marginTop: 4 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, letterSpacing: '0.18em', textTransform: 'uppercase', color: '#848e9c' }}>Partners</span>
            <span style={{ fontSize: 14, fontWeight: 800, color: '#eaecef' }}>CoinMarketCap</span>
            <span style={{ color: '#2b3139' }}>·</span>
            <span style={{ fontSize: 14, fontWeight: 800, color: '#f0b90b' }}>BNB Chain</span>
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '5px 12px', borderRadius: 999, fontSize: 12, fontWeight: 700,
              background: 'rgba(14,203,129,0.1)', color: '#0ecb81', border: '1px solid rgba(14,203,129,0.25)',
            }}>
              <span className="live-dot" style={{ width: 6, height: 6, borderRadius: '50%', background: '#0ecb81', display: 'inline-block' }} />
              Track 2 · Live
            </div>
          </motion.div>
        </motion.div>

        {/* Right — floating signal card over the globe */}
        {!isMobile && (
          <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.8, ease: 'easeOut', delay: 0.2 }} style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', position: 'relative' }}>
            <SignalCard />
          </motion.div>
        )}
      </div>

      <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 96, background: 'linear-gradient(to bottom, transparent, #0b0e11)', pointerEvents: 'none', zIndex: 5 }} />
    </section>
  )
}
