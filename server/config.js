import 'dotenv/config';

const port = Number(process.env.PORT) || 3000;

export const config = {
  port,
  anthropicApiKey: process.env.ANTHROPIC_API_KEY || '',
  model: process.env.JARVIS_MODEL || 'claude-sonnet-5-5',
  timeZone: process.env.JARVIS_TIMEZONE || 'America/Sao_Paulo',
  dataDir: process.env.JARVIS_DATA_DIR || 'data',
  google: {
    clientId: process.env.GOOGLE_CLIENT_ID || '',
    clientSecret: process.env.GOOGLE_CLIENT_SECRET || '',
    redirectUri: process.env.GOOGLE_REDIRECT_URI || `http://localhost:${port}/auth/google/callback`,
  },
};
