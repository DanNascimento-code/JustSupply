/* oxlint-disable react/only-export-components */

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

export type Language = 'en' | 'pt-BR' | 'es-419'

const english = {
  pageTitle: 'JustSupply | Consumer evidence',
  metaDescription: 'Consumer product research with cited ethical and environmental evidence.',
  home: 'JustSupply home',
  appBadge: 'Consumer evidence search',
  footerTagline: 'Evidence before conclusions.',
  languageLabel: 'Language',
  eyebrow: 'Ethical shopping, grounded in evidence',
  heroTitle: 'Look beyond the label.',
  heroDescription:
    'Search a product, brand, or barcode to examine vegan composition, environmental impacts such as deforestation and sustainability, minority employment, and inclusion. Research cited public sources with Gemini or ask a question through evidence-grounded RAG.',
  searchLabel: 'Product, brand, or barcode',
  searchPlaceholder: 'Try a brand, product name, or barcode',
  searching: 'Searching…',
  searchEvidence: 'Search evidence',
  searchNote: "Search runs only when submitted to respect the public catalog's request limit.",
  exampleSearches: 'Example searches',
  tryExample: 'Try an example',
  resultGuide: 'How to read a result',
  noEvidenceTitle: 'No evidence is not the same as negative evidence.',
  noEvidenceBody:
    'JustSupply separates a documented concern from information that a company has not disclosed. Every finding shows its scope, source count, and verification limitations.',
  supported: 'Supported',
  concern: 'Concern',
  notDisclosed: 'Not disclosed',
  checkingEvidence: 'Checking the available evidence…',
  waitMessage: 'This can take a few seconds.',
  searchFailed: 'We could not complete this search.',
  searchResult: 'Search result',
  noMatches: 'No matches for “{query}”',
  oneMatch: '1 match for “{query}”',
  manyMatches: '{count} matches for “{query}”',
  barcodeSearch: 'Barcode search',
  textSearch: 'Text search',
  noCatalogRecord: 'No catalog record was found',
  noCatalogHelp: 'Check the spelling or try the barcode printed on the package.',
  findCatalog: 'Find a catalog record',
  findCatalogBody: 'Use a product name, its brand, or the barcode on its package.',
  readDimension: 'Read each dimension',
  readDimensionBody: 'See favorable evidence, concerns, uncertainty, and disclosure gaps separately.',
  inspectSource: 'Inspect the source',
  inspectSourceBody:
    'Research one result with Gemini, inspect every citation, and ask follow-up questions grounded in retrieved evidence.',
  updateUnavailable: 'Update date not available',
  updated: 'Updated {date}',
  packageAlt: '{name} package',
  brandNotDisclosed: 'Brand not disclosed',
  barcode: 'Barcode {barcode}',
  evidenceCoverage: 'Evidence coverage',
  aiResearch: 'AI-assisted public research',
  sourcesResearched: '{count} cited sources researched',
  researchPrompt: 'Research this product and brand with Gemini',
  researchExplanation:
    'Gemini searches public sources. JustSupply keeps only claims with traceable citations and labels evidence limitations.',
  researching: 'Researching sources…',
  refreshResearch: 'Refresh research',
  researchGemini: 'Research with Gemini',
  researchFailed: 'The public-source research is unavailable right now. Please try again later.',
  catalogDataFrom: 'Catalog data from {source}',
  inspectCatalog: 'Inspect catalog source',
  evidenceSupports: 'Evidence supports',
  mixedEvidence: 'Mixed evidence',
  concernFound: 'Concern found',
  unknown: 'Unknown',
  catalogData: 'Catalog data',
  multipleSources: 'Multiple sources',
  singleSource: 'Single source',
  unverified: 'Unverified',
  productEvidence: 'Product-level evidence',
  brandEvidence: 'Brand-level evidence',
  limitations: 'Limitations',
  askEvidence: 'Ask the evidence',
  specificQuestion: 'Have a specific question about {name}?',
  assistantExplanation:
    'Answers use RAG over cited research for this product. The model must cite retrieved evidence or say that available sources are insufficient.',
  questionLabel: 'Question about {name}',
  questionPlaceholder: 'What evidence exists about minority employment?',
  researchFirst: 'Run public research before asking a question',
  checking: 'Checking evidence…',
  ask: 'Ask',
  questionFailed: 'The evidence assistant is unavailable right now. Please try again later.',
  insufficientEvidence: 'Insufficient evidence',
  evidenceAnswer: 'Evidence-based answer',
  match: '{value}% match',
} as const

type TranslationKey = keyof typeof english
type Dictionary = Record<TranslationKey, string>

const portuguese: Dictionary = {
  pageTitle: 'JustSupply | Evidências para consumidores', metaDescription: 'Pesquisa de produtos com evidências éticas e ambientais citadas.',
  home: 'Início do JustSupply', appBadge: 'Busca de evidências para consumidores',
  footerTagline: 'Evidências antes de conclusões.', languageLabel: 'Idioma',
  eyebrow: 'Consumo ético, fundamentado em evidências', heroTitle: 'Vá além do rótulo.',
  heroDescription: 'Pesquise um produto, marca ou código de barras para analisar composição vegana, impactos ambientais como desmatamento e sustentabilidade, emprego de minorias e inclusão. Pesquise fontes públicas citadas com o Gemini ou faça uma pergunta por meio de RAG fundamentado em evidências.',
  searchLabel: 'Produto, marca ou código de barras', searchPlaceholder: 'Digite uma marca, nome de produto ou código de barras',
  searching: 'Pesquisando…', searchEvidence: 'Pesquisar evidências',
  searchNote: 'A busca ocorre somente após o envio para respeitar o limite de requisições do catálogo público.',
  exampleSearches: 'Exemplos de busca', tryExample: 'Teste um exemplo', resultGuide: 'Como interpretar um resultado',
  noEvidenceTitle: 'Ausência de evidência não é o mesmo que evidência negativa.',
  noEvidenceBody: 'O JustSupply separa uma preocupação documentada de informações que uma empresa não divulgou. Cada conclusão mostra seu escopo, número de fontes e limitações de verificação.',
  supported: 'Sustentado', concern: 'Preocupação', notDisclosed: 'Não divulgado',
  checkingEvidence: 'Verificando as evidências disponíveis…', waitMessage: 'Isso pode levar alguns segundos.',
  searchFailed: 'Não foi possível concluir esta busca.', searchResult: 'Resultado da busca',
  noMatches: 'Nenhum resultado para “{query}”', oneMatch: '1 resultado para “{query}”', manyMatches: '{count} resultados para “{query}”',
  barcodeSearch: 'Busca por código de barras', textSearch: 'Busca por texto', noCatalogRecord: 'Nenhum registro foi encontrado no catálogo',
  noCatalogHelp: 'Confira a escrita ou tente o código de barras impresso na embalagem.', findCatalog: 'Encontre um registro no catálogo',
  findCatalogBody: 'Use o nome do produto, sua marca ou o código de barras da embalagem.', readDimension: 'Leia cada dimensão',
  readDimensionBody: 'Veja separadamente evidências favoráveis, preocupações, incertezas e lacunas de divulgação.', inspectSource: 'Consulte a fonte',
  inspectSourceBody: 'Pesquise um resultado com o Gemini, consulte cada citação e faça perguntas adicionais fundamentadas nas evidências recuperadas.',
  updateUnavailable: 'Data de atualização indisponível', updated: 'Atualizado em {date}', packageAlt: 'Embalagem de {name}',
  brandNotDisclosed: 'Marca não divulgada', barcode: 'Código de barras {barcode}', evidenceCoverage: 'Cobertura de evidências',
  aiResearch: 'Pesquisa pública auxiliada por IA', sourcesResearched: '{count} fontes citadas pesquisadas',
  researchPrompt: 'Pesquise este produto e sua marca com o Gemini', researchExplanation: 'O Gemini pesquisa fontes públicas. O JustSupply mantém apenas afirmações com citações rastreáveis e identifica as limitações das evidências.',
  researching: 'Pesquisando fontes…', refreshResearch: 'Atualizar pesquisa', researchGemini: 'Pesquisar com Gemini',
  researchFailed: 'A pesquisa em fontes públicas está indisponível no momento. Tente novamente mais tarde.',
  catalogDataFrom: 'Dados do catálogo: {source}', inspectCatalog: 'Consultar fonte do catálogo', evidenceSupports: 'Evidências sustentam',
  mixedEvidence: 'Evidências divergentes', concernFound: 'Preocupação encontrada', unknown: 'Desconhecido', catalogData: 'Dados do catálogo',
  multipleSources: 'Múltiplas fontes', singleSource: 'Fonte única', unverified: 'Não verificado', productEvidence: 'Evidência no nível do produto',
  brandEvidence: 'Evidência no nível da marca', limitations: 'Limitações', askEvidence: 'Pergunte às evidências',
  specificQuestion: 'Tem uma pergunta específica sobre {name}?', assistantExplanation: 'As respostas usam RAG sobre a pesquisa citada deste produto. O modelo deve citar a evidência recuperada ou informar que as fontes disponíveis são insuficientes.',
  questionLabel: 'Pergunta sobre {name}', questionPlaceholder: 'Quais evidências existem sobre o emprego de minorias?', researchFirst: 'Execute a pesquisa pública antes de fazer uma pergunta',
  checking: 'Verificando evidências…', ask: 'Perguntar', insufficientEvidence: 'Evidências insuficientes', evidenceAnswer: 'Resposta baseada em evidências', match: '{value}% de correspondência',
  questionFailed: 'O assistente de evidências está indisponível no momento. Tente novamente mais tarde.',
}

const spanish: Dictionary = {
  pageTitle: 'JustSupply | Evidencia para consumidores', metaDescription: 'Investigación de productos con evidencia ética y ambiental citada.',
  home: 'Inicio de JustSupply', appBadge: 'Búsqueda de evidencia para consumidores', footerTagline: 'Evidencia antes que conclusiones.',
  languageLabel: 'Idioma', eyebrow: 'Consumo ético, basado en evidencia', heroTitle: 'Mira más allá de la etiqueta.',
  heroDescription: 'Busca un producto, marca o código de barras para analizar composición vegana, impactos ambientales como deforestación y sostenibilidad, empleo de minorías e inclusión. Investiga fuentes públicas citadas con Gemini o haz una pregunta mediante RAG basado en evidencia.',
  searchLabel: 'Producto, marca o código de barras', searchPlaceholder: 'Prueba una marca, nombre de producto o código de barras', searching: 'Buscando…',
  searchEvidence: 'Buscar evidencia', searchNote: 'La búsqueda se ejecuta solamente al enviarla para respetar el límite de solicitudes del catálogo público.',
  exampleSearches: 'Ejemplos de búsqueda', tryExample: 'Prueba un ejemplo', resultGuide: 'Cómo interpretar un resultado',
  noEvidenceTitle: 'La falta de evidencia no es lo mismo que evidencia negativa.', noEvidenceBody: 'JustSupply separa una preocupación documentada de la información que una empresa no divulgó. Cada conclusión muestra su alcance, cantidad de fuentes y limitaciones de verificación.',
  supported: 'Respaldado', concern: 'Preocupación', notDisclosed: 'No divulgado', checkingEvidence: 'Revisando la evidencia disponible…',
  waitMessage: 'Esto puede tardar unos segundos.', searchFailed: 'No pudimos completar esta búsqueda.', searchResult: 'Resultado de búsqueda',
  noMatches: 'Sin resultados para “{query}”', oneMatch: '1 resultado para “{query}”', manyMatches: '{count} resultados para “{query}”',
  barcodeSearch: 'Búsqueda por código de barras', textSearch: 'Búsqueda por texto', noCatalogRecord: 'No se encontró un registro en el catálogo',
  noCatalogHelp: 'Revisa la escritura o prueba el código de barras impreso en el envase.', findCatalog: 'Encuentra un registro del catálogo',
  findCatalogBody: 'Usa el nombre del producto, su marca o el código de barras del envase.', readDimension: 'Lee cada dimensión',
  readDimensionBody: 'Observa por separado evidencia favorable, preocupaciones, incertidumbre y brechas de divulgación.', inspectSource: 'Revisa la fuente',
  inspectSourceBody: 'Investiga un resultado con Gemini, revisa cada cita y haz preguntas adicionales basadas en la evidencia recuperada.',
  updateUnavailable: 'Fecha de actualización no disponible', updated: 'Actualizado el {date}', packageAlt: 'Envase de {name}', brandNotDisclosed: 'Marca no divulgada',
  barcode: 'Código de barras {barcode}', evidenceCoverage: 'Cobertura de evidencia', aiResearch: 'Investigación pública asistida por IA',
  sourcesResearched: '{count} fuentes citadas investigadas', researchPrompt: 'Investiga este producto y su marca con Gemini',
  researchExplanation: 'Gemini busca fuentes públicas. JustSupply conserva solo afirmaciones con citas rastreables e identifica las limitaciones de la evidencia.',
  researching: 'Investigando fuentes…', refreshResearch: 'Actualizar investigación', researchGemini: 'Investigar con Gemini', catalogDataFrom: 'Datos del catálogo: {source}',
  researchFailed: 'La investigación en fuentes públicas no está disponible en este momento. Inténtalo de nuevo más tarde.',
  inspectCatalog: 'Revisar fuente del catálogo', evidenceSupports: 'La evidencia respalda', mixedEvidence: 'Evidencia mixta', concernFound: 'Preocupación encontrada',
  unknown: 'Desconocido', catalogData: 'Datos del catálogo', multipleSources: 'Múltiples fuentes', singleSource: 'Fuente única', unverified: 'No verificado',
  productEvidence: 'Evidencia a nivel de producto', brandEvidence: 'Evidencia a nivel de marca', limitations: 'Limitaciones', askEvidence: 'Pregunta a la evidencia',
  specificQuestion: '¿Tienes una pregunta específica sobre {name}?', assistantExplanation: 'Las respuestas usan RAG sobre la investigación citada de este producto. El modelo debe citar la evidencia recuperada o indicar que las fuentes disponibles son insuficientes.',
  questionLabel: 'Pregunta sobre {name}', questionPlaceholder: '¿Qué evidencia existe sobre el empleo de minorías?', researchFirst: 'Ejecuta la investigación pública antes de hacer una pregunta',
  checking: 'Revisando evidencia…', ask: 'Preguntar', insufficientEvidence: 'Evidencia insuficiente', evidenceAnswer: 'Respuesta basada en evidencia', match: '{value}% de coincidencia',
  questionFailed: 'El asistente de evidencia no está disponible en este momento. Inténtalo de nuevo más tarde.',
}

const dictionaries: Record<Language, Dictionary> = { en: english, 'pt-BR': portuguese, 'es-419': spanish }
const languageStorageKey = 'justsupply-language'

interface I18nValue {
  language: Language
  setLanguage: (language: Language) => void
  t: (key: TranslationKey, values?: Record<string, string | number>) => string
}

const I18nContext = createContext<I18nValue | null>(null)

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<Language>(() => {
    const saved = window.localStorage.getItem(languageStorageKey)
    return saved === 'pt-BR' || saved === 'es-419' ? saved : 'en'
  })

  useEffect(() => {
    window.localStorage.setItem(languageStorageKey, language)
    document.documentElement.lang = language
    document.title = dictionaries[language].pageTitle
    document.querySelector('meta[name="description"]')?.setAttribute(
      'content',
      dictionaries[language].metaDescription,
    )
  }, [language])

  const value = useMemo<I18nValue>(() => ({
    language,
    setLanguage,
    t: (key, values = {}) => Object.entries(values).reduce(
      (text, [name, replacement]) => text.replaceAll(`{${name}}`, String(replacement)),
      dictionaries[language][key],
    ),
  }), [language])

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n(): I18nValue {
  const context = useContext(I18nContext)
  if (context === null) throw new Error('useI18n must be used inside I18nProvider')
  return context
}
