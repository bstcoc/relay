export const CONTACT = "mailto:bastien.cochet.pro@gmail.com?subject=Relay";

export const REPOSITORY = "https://github.com/bstcoc/relay";

const thin = " ";

export function count(value: number) {
  return Math.round(value).toLocaleString("en-US").replaceAll(",", thin);
}
