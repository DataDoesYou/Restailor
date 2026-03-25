import { ImageResponse } from 'next/og';

// Route segment config
export const runtime = 'edge';

// Image metadata
export const alt = 'Restailor';
export const size = {
  width: 1200,
  height: 630,
};
export const contentType = 'image/png';

export default async function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          fontSize: 64,
          background: 'linear-gradient(135deg, #1e3a8a 0%, #000000 100%)',
          color: 'white',
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '80px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 40 }}>
          <div
            style={{
              width: 100,
              height: 100,
              backgroundColor: '#3b82f6',
              borderRadius: '24px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginRight: 32,
              boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
            }}
          >
            <span style={{ fontSize: 72, fontWeight: 'bold' }}>R</span>
          </div>
          <h1 style={{ fontSize: 96, fontWeight: 900, margin: 0 }}>Restailor</h1>
        </div>
        <p style={{
          fontSize: 48,
          fontWeight: 400,
          color: '#93c5fd',
          textAlign: 'center',
          margin: 0,
          lineHeight: 1.4,
          textShadow: '0 2px 4px rgba(0,0,0,0.3)',
        }}>
          Tailor Your Resume to Any Job with AI
        </p>
      </div>
    ),
    {
      ...size,
    }
  );
}
