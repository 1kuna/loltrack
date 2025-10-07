type QueueDef = { id: number, map: string, description: string|null }

// Common SR/ARAM/Clash queues + recent Quickplay and bots.
const COMMON: QueueDef[] = [
  { id: 400, map: "Summoner's Rift", description: 'Normal Draft' },
  { id: 420, map: "Summoner's Rift", description: 'Ranked Solo/Duo' },
  { id: 430, map: "Summoner's Rift", description: 'Normal Blind' },
  { id: 440, map: "Summoner's Rift", description: 'Ranked Flex' },
  { id: 450, map: 'Howling Abyss', description: 'ARAM' },
  { id: 480, map: "Summoner's Rift", description: 'Normal (Legacy)' },
  { id: 490, map: "Summoner's Rift", description: 'Quickplay' },
  { id: 700, map: "Summoner's Rift", description: 'Clash' },
  { id: 830, map: "Summoner's Rift", description: 'Co-op vs AI (Intro)' },
  { id: 840, map: "Summoner's Rift", description: 'Co-op vs AI (Beginner)' },
  { id: 850, map: "Summoner's Rift", description: 'Co-op vs AI (Intermediate)' },
  { id: 870, map: "Summoner's Rift", description: 'Co-op vs AI (Intro)' },
  { id: 880, map: "Summoner's Rift", description: 'Co-op vs AI (Beginner)' },
  { id: 890, map: "Summoner's Rift", description: 'Co-op vs AI (Intermediate)' },
  { id: 900, map: "Summoner's Rift", description: 'ARURF' },
  { id: 1010, map: "Summoner's Rift", description: 'Snow URF' },
  { id: 1020, map: "Summoner's Rift", description: 'One for All' },
]

const MAP: Record<number, QueueDef> = Object.fromEntries(COMMON.map(q => [q.id, q]))

export function queueName(id?: number): string {
  if (id == null) return 'Unknown'
  const q = MAP[id]
  if (q) return q.description || `${q.map}`
  return `Queue ${id}`
}
