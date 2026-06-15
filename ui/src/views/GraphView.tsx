import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Network, Search, X } from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { Graph } from "@/types"
import { Button } from "@/components/ui/button"

interface Node {
  id: string
  title: string
  type: string
  tags: string[]
  x: number
  y: number
}

const W = 1000
const H = 700

const TYPE_COLOR: Record<string, string> = {
  concept: "#2bb673",
  entity: "#a855f7",
  synthesis: "#06b6d4",
  decision: "#e8873a",
  research: "#3b82f6",
  project: "#eab308",
}
function colorFor(type: string) {
  return TYPE_COLOR[type] ?? "#94a3b8"
}

/** Run a few hundred force-sim iterations to lay out the graph deterministically. */
function layout(graph: Graph): Node[] {
  const nodes: Node[] = graph.nodes.map((n, i) => {
    const angle = (i / Math.max(1, graph.nodes.length)) * Math.PI * 2
    return {
      ...n,
      tags: n.tags ?? [],
      x: W / 2 + Math.cos(angle) * 250,
      y: H / 2 + Math.sin(angle) * 250,
    }
  })
  const index = new Map<string, number>()
  nodes.forEach((n, i) => {
    index.set(n.id, i)
    index.set(n.title.toLowerCase(), i)
  })
  const idx = (key: string) =>
    index.get(key) ?? index.get(key.toLowerCase())
  const edges = graph.edges
    .map((e) => [idx(e.from), idx(e.to)] as const)
    .filter((e): e is readonly [number, number] => e[0] != null && e[1] != null)

  const REPULSION = 12000
  const SPRING = 0.02
  const SPRING_LEN = 120
  const CENTER = 0.008

  for (let iter = 0; iter < 350; iter++) {
    const fx = new Array(nodes.length).fill(0)
    const fy = new Array(nodes.length).fill(0)
    // repulsion
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        let dx = nodes[i].x - nodes[j].x
        let dy = nodes[i].y - nodes[j].y
        const d2 = dx * dx + dy * dy || 0.01
        const f = REPULSION / d2
        const d = Math.sqrt(d2)
        dx /= d
        dy /= d
        fx[i] += dx * f
        fy[i] += dy * f
        fx[j] -= dx * f
        fy[j] -= dy * f
      }
    }
    // springs
    for (const [a, b] of edges) {
      const dx = nodes[b].x - nodes[a].x
      const dy = nodes[b].y - nodes[a].y
      const d = Math.sqrt(dx * dx + dy * dy) || 0.01
      const f = (d - SPRING_LEN) * SPRING
      fx[a] += (dx / d) * f
      fy[a] += (dy / d) * f
      fx[b] -= (dx / d) * f
      fy[b] -= (dy / d) * f
    }
    // centering + integrate
    for (let i = 0; i < nodes.length; i++) {
      fx[i] += (W / 2 - nodes[i].x) * CENTER
      fy[i] += (H / 2 - nodes[i].y) * CENTER
      nodes[i].x += Math.max(-15, Math.min(15, fx[i]))
      nodes[i].y += Math.max(-15, Math.min(15, fy[i]))
    }
  }
  return nodes
}

export function GraphView() {
  const navigate = useNavigate()
  const [graph, setGraph] = useState<Graph | null>(null)
  const [nodes, setNodes] = useState<Node[]>([])
  const [selected, setSelected] = useState<Node | null>(null)
  // Type filter: a set of *active* types (all active by default, #193).
  const [activeTypes, setActiveTypes] = useState<Set<string>>(new Set())
  const [tagFilter, setTagFilter] = useState<string>("")
  const [search, setSearch] = useState("")
  const [matchIdx, setMatchIdx] = useState(0)
  const [focusId, setFocusId] = useState<string | null>(null)
  const [depth, setDepth] = useState<1 | 2>(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const dragRef = useRef<{ id: string } | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    api
      .graph()
      .then((g) => {
        setGraph(g)
        const laid = layout(g)
        setNodes(laid)
        setActiveTypes(new Set(laid.map((n) => n.type)))
      })
      .catch((e) => toast.error((e as Error).message))
  }, [])

  const types = useMemo(
    () => [...new Set(nodes.map((n) => n.type))].sort(),
    [nodes],
  )
  const tags = useMemo(
    () => [...new Set(nodes.flatMap((n) => n.tags))].sort(),
    [nodes],
  )
  // Edges may reference a node by path (id) or by title (raw wikilink target),
  // so index by both for resolution.
  const nodePos = useMemo(() => {
    const m = new Map<string, Node>()
    for (const n of nodes) {
      m.set(n.id, n)
      m.set(n.title.toLowerCase(), n)
    }
    return m
  }, [nodes])
  const resolve = (key: string) =>
    nodePos.get(key) ?? nodePos.get(key.toLowerCase())

  // Adjacency by node id (undirected), for focus-mode BFS and degree count.
  const adjacency = useMemo(() => {
    const adj = new Map<string, Set<string>>()
    for (const n of nodes) adj.set(n.id, new Set())
    for (const e of graph?.edges ?? []) {
      const a = resolve(e.from)
      const b = resolve(e.to)
      if (!a || !b || a.id === b.id) continue
      adj.get(a.id)!.add(b.id)
      adj.get(b.id)!.add(a.id)
    }
    return adj
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, graph])

  // Nodes within `depth` hops of the focused node (inclusive). Empty = no focus.
  const focusSet = useMemo(() => {
    if (!focusId) return null
    const seen = new Set<string>([focusId])
    let frontier = [focusId]
    for (let d = 0; d < depth; d++) {
      const next: string[] = []
      for (const id of frontier) {
        for (const nb of adjacency.get(id) ?? []) {
          if (!seen.has(nb)) {
            seen.add(nb)
            next.push(nb)
          }
        }
      }
      frontier = next
    }
    return seen
  }, [focusId, depth, adjacency])

  const isVisible = (n: Node) =>
    activeTypes.has(n.type) && (!tagFilter || n.tags.includes(tagFilter))

  // Search matches: visible nodes whose title contains the query.
  const matches = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return [] as Node[]
    return nodes.filter((n) => isVisible(n) && n.title.toLowerCase().includes(q))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, nodes, activeTypes, tagFilter])

  // Centre the viewport on a node by panning the content group.
  const centerOn = (n: Node) => setPan({ x: W / 2 - n.x, y: H / 2 - n.y })

  // Whenever the match set changes, snap to the first match.
  useEffect(() => {
    if (matches.length > 0) {
      setMatchIdx(0)
      centerOn(matches[0])
    }
  }, [matches])

  const cycleMatch = () => {
    if (matches.length === 0) return
    const next = (matchIdx + 1) % matches.length
    setMatchIdx(next)
    centerOn(matches[next])
  }
  const currentMatchId = matches[matchIdx]?.id
  const matchIds = useMemo(() => new Set(matches.map((m) => m.id)), [matches])

  const toggleType = (t: string) =>
    setActiveTypes((prev) => {
      const next = new Set(prev)
      if (next.has(t)) next.delete(t)
      else next.add(t)
      return next
    })

  const resetView = () => {
    setActiveTypes(new Set(types))
    setTagFilter("")
    setSearch("")
    setFocusId(null)
    setSelected(null)
    setPan({ x: 0, y: 0 })
  }

  function toSvg(e: React.PointerEvent): { x: number; y: number } {
    const svg = svgRef.current!
    const rect = svg.getBoundingClientRect()
    return {
      x: ((e.clientX - rect.left) / rect.width) * W,
      y: ((e.clientY - rect.top) / rect.height) * H,
    }
  }

  const degree = (id: string) => adjacency.get(id)?.size ?? 0

  return (
    <div className="relative flex-1 overflow-hidden">
      {/* toolbar */}
      <div className="absolute left-4 top-4 z-10 flex max-w-[calc(100%-2rem)] flex-wrap items-center gap-2">
        <h1 className="flex items-center gap-1.5 rounded-md border bg-card px-2.5 py-1.5 font-display text-[13px] font-semibold shadow-sm">
          <Network className="size-4 text-primary" /> Graph
        </h1>

        {/* type toggles (legend doubles as filter) */}
        <div className="flex flex-wrap gap-1 rounded-md border bg-card p-1 shadow-sm">
          {types.map((t) => {
            const on = activeTypes.has(t)
            return (
              <button
                key={t}
                onClick={() => toggleType(t)}
                className={`flex items-center gap-1 rounded px-2 py-0.5 text-[11px] transition ${
                  on ? "bg-secondary font-medium" : "text-muted-foreground opacity-60"
                }`}
              >
                <span
                  className="size-2 rounded-full"
                  style={{ background: colorFor(t) }}
                />
                {t}
              </button>
            )
          })}
        </div>

        {/* tag filter */}
        {tags.length > 0 && (
          <select
            value={tagFilter}
            onChange={(e) => setTagFilter(e.target.value)}
            className="h-[28px] rounded-md border bg-card px-2 text-[11px] shadow-sm"
          >
            <option value="">all tags</option>
            {tags.map((t) => (
              <option key={t} value={t}>
                #{t}
              </option>
            ))}
          </select>
        )}

        {/* node search */}
        <div className="flex items-center gap-1 rounded-md border bg-card px-2 shadow-sm">
          <Search className="size-3.5 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault()
                cycleMatch()
              }
            }}
            placeholder="find node…"
            className="h-[28px] w-28 bg-transparent text-[11px] outline-none"
          />
          {search && (
            <span className="text-[10px] text-muted-foreground">
              {matches.length ? `${matchIdx + 1}/${matches.length}` : "0"}
            </span>
          )}
        </div>

        {/* focus depth toggle */}
        <div className="flex items-center gap-1 rounded-md border bg-card p-1 text-[11px] shadow-sm">
          <span className="px-1 text-muted-foreground">focus</span>
          {[1, 2].map((d) => (
            <button
              key={d}
              onClick={() => setDepth(d as 1 | 2)}
              className={`rounded px-1.5 py-0.5 ${
                depth === d ? "bg-secondary font-medium" : "text-muted-foreground"
              }`}
            >
              {d}-hop
            </button>
          ))}
        </div>

        <Button size="sm" variant="ghost" className="h-[28px] gap-1 px-2" onClick={resetView}>
          <X className="size-3.5" /> reset
        </Button>
        {focusId && (
          <span className="rounded-md border bg-primary/10 px-2 py-1 text-[11px] text-primary">
            focusing — click background to exit
          </span>
        )}
      </div>

      {graph && graph.nodes.length === 0 && (
        <div className="flex h-full items-center justify-center text-[13px] text-muted-foreground">
          No pages to graph yet.
        </div>
      )}

      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="h-full w-full"
        onPointerMove={(e) => {
          if (!dragRef.current) return
          const { x, y } = toSvg(e)
          const id = dragRef.current.id
          setNodes((ns) =>
            ns.map((n) =>
              n.id === id ? { ...n, x: x - pan.x, y: y - pan.y } : n,
            ),
          )
        }}
        onPointerUp={() => (dragRef.current = null)}
        onPointerLeave={() => (dragRef.current = null)}
        onClick={() => {
          // Click on empty background exits focus mode.
          if (focusId) setFocusId(null)
        }}
      >
        <g transform={`translate(${pan.x},${pan.y})`}>
          {/* edges */}
          {graph?.edges.map((e, i) => {
            const a = resolve(e.from)
            const b = resolve(e.to)
            if (!a || !b) return null
            if (!isVisible(a) || !isVisible(b)) return null
            const inFocus =
              !focusSet || (focusSet.has(a.id) && focusSet.has(b.id))
            return (
              <line
                key={i}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke="currentColor"
                className="text-border"
                strokeWidth={1}
                opacity={inFocus ? 0.5 : 0.08}
              />
            )
          })}
          {/* nodes */}
          {nodes.map((n) => {
            if (!isVisible(n)) return null
            const inFocus = !focusSet || focusSet.has(n.id)
            const isMatch = matchIds.has(n.id)
            const isCurrent = currentMatchId === n.id
            const isSel = selected?.id === n.id
            const highlight = isSel || isCurrent
            return (
              <g
                key={n.id}
                transform={`translate(${n.x},${n.y})`}
                opacity={inFocus ? (isMatch && !isCurrent ? 0.9 : 1) : 0.15}
                className="cursor-pointer"
                onPointerDown={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  dragRef.current = { id: n.id }
                  setSelected(n)
                }}
                onClick={(e) => {
                  e.stopPropagation()
                  setFocusId(n.id)
                }}
                onDoubleClick={() =>
                  navigate(`/wiki?path=${encodeURIComponent(n.id)}`)
                }
              >
                <title>{`${n.title} • ${n.type} • ${degree(n.id)} connections`}</title>
                <circle
                  r={highlight ? 10 : isMatch ? 8 : 6}
                  fill={colorFor(n.type)}
                  stroke={
                    isCurrent
                      ? "var(--primary)"
                      : highlight
                        ? "var(--foreground)"
                        : "white"
                  }
                  strokeWidth={highlight ? 2.5 : isMatch ? 2 : 1.5}
                />
                <text
                  x={12}
                  y={4}
                  className="fill-foreground"
                  style={{ fontSize: 11, fontFamily: "var(--font-body)" }}
                >
                  {n.title}
                </text>
              </g>
            )
          })}
        </g>
      </svg>

      {/* side panel */}
      {selected && (
        <div className="absolute right-4 top-4 z-10 w-[260px] rounded-lg border bg-card p-4 shadow-md">
          <div className="flex items-center gap-2">
            <span
              className="size-3 rounded-full"
              style={{ background: colorFor(selected.type) }}
            />
            <span className="font-display text-[14px] font-semibold">
              {selected.title}
            </span>
          </div>
          <div className="mt-1 text-[12px] text-muted-foreground">
            {selected.type} · {degree(selected.id)} connections
          </div>
          {selected.tags.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {selected.tags.map((t) => (
                <button
                  key={t}
                  onClick={() => setTagFilter(t)}
                  className="rounded bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground hover:text-foreground"
                >
                  #{t}
                </button>
              ))}
            </div>
          )}
          <div className="mt-3 flex gap-2">
            <Button
              size="sm"
              variant="secondary"
              className="flex-1"
              onClick={() => setFocusId(selected.id)}
            >
              Focus
            </Button>
            <Button
              size="sm"
              className="flex-1"
              onClick={() => navigate(`/wiki?path=${encodeURIComponent(selected.id)}`)}
            >
              Open →
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
