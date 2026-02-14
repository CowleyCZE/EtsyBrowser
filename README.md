# Next.js Starter Template

A minimal Next.js starter template designed for AI-assisted development. It provides a clean foundation that can be extended to build any type of web application.

## Features

- **Next.js 16** with App Router
- **TypeScript** for type safety
- **Tailwind CSS 4** for styling
- **ESLint** for code quality
- **Recipe system** for common additions (database, auth)
- **Memory bank** for AI context persistence

## Quick Start

```bash
# Install dependencies
bun install

# Start development server
bun dev
```

Open [http://localhost:3000](http://localhost:3000) to view your app.

## Adding Features

### Add a new page

Create a file at `src/app/[route]/page.tsx`:
```tsx
export default function NewPage() {
  return <div>New page content</div>;
}
```

### Add components

Create `src/components/` directory and add components:
```tsx
// src/components/ui/Button.tsx
export function Button({ children }: { children: React.ReactNode }) {
  return <button className="px-4 py-2 bg-blue-600 text-white rounded">{children}</button>;
}
```

### Add a database

Follow `.kilocode/recipes/add-database.md`

### Add API routes

Create `src/app/api/[route]/route.ts`:
```tsx
import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({ message: "Hello" });
}
```

## Available Scripts

| Command | Purpose |
|---------|---------|
| `bun install` | Install dependencies |
| `bun dev` | Start development server |
| `bun build` | Build production app |
| `bun start` | Start production server |
| `bun lint` | Check code quality |
| `bun typecheck` | Type checking |

## Project Structure

```
/
├── .gitignore
├── package.json
├── next.config.ts
├── tsconfig.json
├── postcss.config.mjs
├── eslint.config.mjs
├── public/
│   └── .gitkeep
└── src/
    └── app/
        ├── layout.tsx      # Root layout
        ├── page.tsx       # Home page
        └── globals.css    # Global styles
```

## Documentation

- [Next.js Docs](https://nextjs.org/docs)
- [Tailwind CSS](https://tailwindcss.com/docs)
- [TypeScript](https://www.typescriptlang.org/docs)
