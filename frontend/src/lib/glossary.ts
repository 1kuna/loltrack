export type GlossaryEntry = {
  key: string
  term: string
  definition: string
  aliases?: string[]
}

const ENTRIES: GlossaryEntry[] = [
  {
    key: 'CS10',
    term: 'CS @ 10:00',
    definition: 'How many minions you have last-hit by the 10 minute mark.',
    aliases: ['cs@10', 'cs10'],
  },
  {
    key: 'CS14',
    term: 'CS @ 14:00',
    definition: 'Your creep score by the 14 minute timing—roughly two full waves after plates fall.',
    aliases: ['cs@14', 'cs14'],
  },
  {
    key: 'DL14',
    term: 'No deaths until 14:00',
    definition: 'Share of your games where you avoid dying before 14:00. Higher is better.',
    aliases: ['deaths<14', 'no-deaths-14'],
  },
  {
    key: 'GD10',
    term: 'Gold lead @ 10:00',
    definition: 'Your net gold difference versus your lane opponent at 10 minutes.',
    aliases: ['gd10', 'gold@10'],
  },
  {
    key: 'XPD10',
    term: 'XP lead @ 10:00',
    definition: 'Experience difference against lane opponent at 10 minutes. +50 means roughly half a wave up.',
    aliases: ['xpd10', 'xp@10'],
  },
  {
    key: 'CtrlWardsPre14',
    term: 'Control wards before 14:00',
    definition: 'How many control wards you buy or place before 14 minutes.',
    aliases: ['ctrl-wards', 'control-wards'],
  },
  {
    key: 'FirstRecall',
    term: 'First recall time',
    definition: 'Timestamp of your first intentional recall. Earlier is usually better—look for well-timed resets.',
    aliases: ['recall', 'first-recall'],
  },
  {
    key: 'KPEarly',
    term: 'Kill participation (0–14)',
    definition: 'Kills + assists you contribute to divided by your team’s kills before 14 minutes.',
    aliases: ['early-kp', 'kp-early'],
  },
  {
    key: 'P50',
    term: 'Median (P50)',
    definition: 'Half of your games land above this value, half below it.',
  },
  {
    key: 'P75',
    term: 'Top quartile (P75)',
    definition: 'The value your better 25% of games achieve or exceed.',
  },
  {
    key: 'KP',
    term: 'Kill participation',
    definition: 'How often you are involved in team kills: (kills + assists) ÷ team kills.',
    aliases: ['k/p', 'kill participation'],
  },
]

const LOOKUP: Record<string, GlossaryEntry> = ENTRIES.reduce((acc, entry) => {
  acc[entry.key.toLowerCase()] = entry
  entry.aliases?.forEach((alias) => {
    acc[alias.toLowerCase()] = entry
  })
  return acc
}, {} as Record<string, GlossaryEntry>)

export function resolveGlossaryEntry(key?: string | null): GlossaryEntry | null {
  if (!key) return null
  return LOOKUP[key.toLowerCase()] ?? null
}

export function getGlossaryEntries(): GlossaryEntry[] {
  return ENTRIES
}
