# Thailand Railway Digital Twin - Frontend

Next.js frontend for the Thailand Railway Digital Twin application.

## Features

- Interactive map with Leaflet showing Thailand railway network
- Real-time train position tracking via WebSocket
- Route and station information panels
- Dark/Light theme support
- Responsive design

## Quick Start

### Prerequisites

- Node.js 23+
- npm or yarn

### Installation

1. Install dependencies:
```bash
npm install
```

2. Copy environment file and configure:
```bash
cp .env.example .env.local
# Edit .env.local with your API URLs
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
│   │   ├── Map/         # Map components
│   │   ├── Schedule/    # Schedule components
│   │   ├── TrainInfo/   # Train info components
│   │   └── ui/          # UI components (shadcn/ui)
│   ├── lib/             # Utilities and hooks
│   │   ├── api/         # API client
│   │   ├── hooks/       # Custom hooks
│   │   └── utils/       # Utility functions
│   ├── types/           # TypeScript types
│   └── styles/          # Global styles
├── public/              # Static assets
└── package.json
```

## License

MIT License
