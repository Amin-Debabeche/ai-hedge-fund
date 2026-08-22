export interface MultiNodeDefinition {
  name: string;
  nodes: {
    componentName: string;
    offsetX: number;
    offsetY: number;
  }[];
  edges: {
    source: string;
    target: string;
  }[];
}

const multiNodeDefinition: Record<string, MultiNodeDefinition> = {
  "Value Investors": {
    name: "Value Investors",
    nodes: [
      { componentName: "Stock Input", offsetX: 0, offsetY: 0 },
      { componentName: "Ben Graham", offsetX: 400, offsetY: -400 },
      { componentName: "Charlie Munger", offsetX: 400, offsetY: 0 },
      { componentName: "Warren Buffett", offsetX: 400, offsetY: 400 },
      { componentName: "Portfolio Manager", offsetX: 800, offsetY: 0 },
    ],
    edges: [
      { source: "Stock Input", target: "Ben Graham" },
      { source: "Stock Input", target: "Charlie Munger" },
      { source: "Stock Input", target: "Warren Buffett" },
      { source: "Ben Graham", target: "Portfolio Manager" },
      { source: "Charlie Munger", target: "Portfolio Manager" },
      { source: "Warren Buffett", target: "Portfolio Manager" },
    ],
  },
  "Data Wizards": {
    name: "Data Wizards",
    nodes: [
      { componentName: "Stock Input", offsetX: 0, offsetY: 0 },
      { componentName: "Technical Analyst", offsetX: 400, offsetY: -550 },
      { componentName: "Fundamentals Analyst", offsetX: 400, offsetY: -200 },
      { componentName: "Sentiment Analyst", offsetX: 400, offsetY: 150 },
      { componentName: "Valuation Analyst", offsetX: 400, offsetY: 500 },
      { componentName: "Portfolio Manager", offsetX: 800, offsetY: 0 },
    ],
    edges: [
      { source: "Stock Input", target: "Technical Analyst" },
      { source: "Stock Input", target: "Fundamentals Analyst" },
      { source: "Stock Input", target: "Sentiment Analyst" },
      { source: "Stock Input", target: "Valuation Analyst" },
      { source: "Technical Analyst", target: "Portfolio Manager" },
      { source: "Fundamentals Analyst", target: "Portfolio Manager" },
      { source: "Sentiment Analyst", target: "Portfolio Manager" },
      { source: "Valuation Analyst", target: "Portfolio Manager" },

    ],
  },
  "Market Mavericks": {
    name: "Market Mavericks",
    nodes: [
      { componentName: "Stock Input", offsetX: 0, offsetY: 0 },
      { componentName: "Michael Burry", offsetX: 400, offsetY: -400 },
      { componentName: "Bill Ackman", offsetX: 400, offsetY: 0 },
      { componentName: "Stanley Druckenmiller", offsetX: 400, offsetY: 400 },
      { componentName: "Portfolio Manager", offsetX: 800, offsetY: 0 },
    ],
    edges: [
      { source: "Stock Input", target: "Michael Burry" },
      { source: "Stock Input", target: "Bill Ackman" },
      { source: "Stock Input", target: "Stanley Druckenmiller" },
      { source: "Michael Burry", target: "Portfolio Manager" },
      { source: "Bill Ackman", target: "Portfolio Manager" },
      { source: "Stanley Druckenmiller", target: "Portfolio Manager" },
    ],
  },
};

export function getMultiNodeDefinition(name: string): MultiNodeDefinition | null {
  return multiNodeDefinition[name] || null;
}

export function isMultiNodeComponent(componentName: string): boolean {
  return componentName === RANDOM_SWARM_NAME || componentName in multiNodeDefinition;
}

export const RANDOM_SWARM_NAME = "Random Swarm";

const RANDOM_SWARM_MIN_ANALYSTS = 2;
const ANALYST_VERTICAL_SPACING = 200;
const ANALYST_OFFSET_X = 400;
const PORTFOLIO_MANAGER_OFFSET_X = 800;

function shuffle<T>(items: T[]): T[] {
  const result = [...items];
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}

/**
 * Builds a "Random Swarm" definition: a Stock Input feeding a random subset
 * of the given analysts (at least 2, at most all of them) into a Portfolio
 * Manager. Regenerated fresh - and reshuffled - every time it's added.
 */
export function generateRandomSwarmDefinition(analystDisplayNames: string[]): MultiNodeDefinition {
  const maxCount = analystDisplayNames.length;
  const minCount = Math.min(RANDOM_SWARM_MIN_ANALYSTS, maxCount);
  const count = minCount + Math.floor(Math.random() * (maxCount - minCount + 1));
  const selected = shuffle(analystDisplayNames).slice(0, count);

  const analystNodes = selected.map((displayName, index) => ({
    componentName: displayName,
    offsetX: ANALYST_OFFSET_X,
    offsetY: (index - (selected.length - 1) / 2) * ANALYST_VERTICAL_SPACING,
  }));

  return {
    name: RANDOM_SWARM_NAME,
    nodes: [
      { componentName: "Stock Input", offsetX: 0, offsetY: 0 },
      ...analystNodes,
      { componentName: "Portfolio Manager", offsetX: PORTFOLIO_MANAGER_OFFSET_X, offsetY: 0 },
    ],
    edges: [
      ...selected.map(displayName => ({ source: "Stock Input", target: displayName })),
      ...selected.map(displayName => ({ source: displayName, target: "Portfolio Manager" })),
    ],
  };
}
