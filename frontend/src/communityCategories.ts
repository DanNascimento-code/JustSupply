import type { FoodCategory } from './types/consumer'

export const FOOD_CATEGORIES: FoodCategory[] = [
  'baby_food',
  'bakery',
  'beverages',
  'biscuits_cookies',
  'breakfast_cereals',
  'candy',
  'chocolate',
  'coffee_tea',
  'condiments_sauces',
  'dairy',
  'dairy_alternatives',
  'desserts',
  'frozen_foods',
  'ice_cream',
  'meat_alternatives',
  'pasta_noodles',
  'ready_meals',
  'snacks_chips',
  'spreads',
  'yogurt',
  'other',
]

export function foodCategoryKey(category: FoodCategory): `foodCategory_${FoodCategory}` {
  return `foodCategory_${category}`
}
