# Thailand Railway Digital Twin - Frontend

Next.js frontend for the Thailand Railway Digital Twin application.

## Features

- Interactive map with Leaflet showing the Thai railway network
- Real-time train position tracking via WebSocket
- Route and station information panels
- Dark/Light theme support
- Responsive design

## Quick Start

### Prerequisites

- Node.js 20+
- npm

### Installation

1. Install dependencies:

```bash
npm install
```

2. Copy the environment file and configure API URLs:

```bash
cp .env.example .env.local
# Edit .env.local if needed
```

3. Start the development server:

```bash
npm run dev
```

4. Open http://localhost:3000 in your browser.

## Development

### Available Scripts

```bash
# Development
npm run dev          # Start development server

# Building
npm run build        # Build for production
npm run start        # Start production server

# Code Quality
npm run lint         # Run ESLint
npm run lint:fix     # Fix ESLint issues
npm run format       # Format with Prettier
npm run type-check   # Run TypeScript check

# Testing
npm run test         # Run tests
npm run test:watch   # Run tests in watch mode
npm run test:coverage # Run tests with coverage
```

## Project Structure

```
frontend/
├── src/
│   ├── app/              # Next.js App Router pages
│   ├── components/       # React components
│   │   ├── Map/           # Map components
│   │   ├── Schedule/      # Schedule components
│   │   ├── TrainInfo/     # Train info components
│   │   └── ui/            # UI components (shadcn/ui)
│   ├── lib/              # Utilities and hooks
│   │   ├── api/           # API client
│   │   ├── hooks/         # Custom hooks
│   │   └── utils/         # Utility functions
│   ├── types/            # TypeScript types
│   └── styles/           # Global styles
├── public/               # Static assets
├── package.json
└── Dockerfile
```

## Tech Details

- Next.js 16+
- React 19
- TypeScript
- Tailwind CSS
- Leaflet / React-Leaflet
- TanStack Query + Zustand

## License

MIT License
