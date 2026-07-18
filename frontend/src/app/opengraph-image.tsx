import { ImageResponse } from 'next/og';

export const alt = 'Thailand train tracker and interactive railway map';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default function OpenGraphImage() {
  return new ImageResponse(
    <div
      style={{
        alignItems: 'center',
        background:
          'linear-gradient(135deg, #09090b 0%, #172554 55%, #0c4a6e 100%)',
        color: '#fafafa',
        display: 'flex',
        height: '100%',
        justifyContent: 'center',
        padding: 72,
        width: '100%',
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', width: '100%' }}>
        <div
          style={{
            color: '#7dd3fc',
            display: 'flex',
            fontSize: 28,
            fontWeight: 700,
            letterSpacing: 6,
            textTransform: 'uppercase',
          }}
        >
          RailTwin · Thailand
        </div>
        <div
          style={{
            display: 'flex',
            fontSize: 72,
            fontWeight: 800,
            lineHeight: 1.05,
            marginTop: 24,
            maxWidth: 980,
          }}
        >
          Thailand Train Tracker &amp; Railway Map
        </div>
        <div
          style={{
            color: '#d4d4d8',
            display: 'flex',
            fontSize: 31,
            marginTop: 32,
          }}
        >
          Routes · stations · timetables · simulated train positions
        </div>
      </div>
    </div>,
    size
  );
}
