import {
  CONTEXT_RANGE_LIMIT,
  PROMPT_PRICE_CNY_LIMIT,
  type RangeValue,
} from "./filterOptions";
import {
  type Category,
  type InputModality,
  type Provider,
  type SupportedParameter,
} from "./models";

export interface ModelFilterState {
  inputModalities: InputModality[];
  contextRange: RangeValue;
  promptPriceCnyRange: RangeValue;
  series: string[];
  categories: Category[];
  supportedParameters: SupportedParameter[];
  distillable: boolean;
  zeroDataRetention: boolean;
  inRegionRouting: boolean;
  provider: Provider | "all";
  modelAuthors: string[];
  showInactive: boolean;
}

export const defaultFilterState: ModelFilterState = {
  inputModalities: [],
  contextRange: CONTEXT_RANGE_LIMIT,
  promptPriceCnyRange: PROMPT_PRICE_CNY_LIMIT,
  series: [],
  categories: [],
  supportedParameters: [],
  distillable: false,
  zeroDataRetention: false,
  inRegionRouting: false,
  provider: "all",
  modelAuthors: [],
  showInactive: false,
};
