<script lang="ts">
  import { untrack } from 'svelte';
  import { t } from '$lib/i18n';
  import { notes, saveNote, deleteNote } from './notes';

  let { slug }: { slug: string } = $props();

  let open = $state(true);
  let draft = $state('');
  let timer: ReturnType<typeof setTimeout> | null = null;

  const existing = $derived($notes[slug]);

  // "saved HH:MM" — derived from the persisted timestamp so it survives
  // collapse/reload and updates the moment a commit lands.
  const savedLabel = $derived.by(() => {
    const iso = $notes[slug]?.updated_at;
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    const p = (n: number) => String(n).padStart(2, '0');
    return `${p(d.getHours())}:${p(d.getMinutes())}`;
  });

  // Hydrate the draft when the slug changes (SvelteKit reuses the component
  // across /researchers/[slug] navigations). Store reads are untracked so our
  // own saveNote() writes don't clobber in-progress typing.
  $effect(() => {
    void slug;
    untrack(() => {
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
      draft = $notes[slug]?.text ?? '';
    });
  });

  $effect(() => {
    return () => {
      if (timer) clearTimeout(timer);
    };
  });

  function commit() {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    const text = draft.trim() === '' ? '' : draft;
    const cur = $notes[slug]?.text ?? '';
    if (text === cur) return; // no change — don't bump updated_at
    if (text === '') deleteNote(slug);
    else saveNote(slug, text);
  }

  function onInput() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(commit, 800);
  }

  function onDelete() {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    draft = '';
    deleteNote(slug);
  }
</script>

<div class="notes-block">
  <button type="button" class="notes-head" onclick={() => (open = !open)} aria-expanded={open}>
    <span class="lbl-mini">{$t('notes.title')}</span>
    <span class="head-right">
      {#if savedLabel}
        <span class="saved">{$t('notes.saved', { time: savedLabel })}</span>
      {/if}
      <span class="caret">{open ? '▾' : '▸'}</span>
    </span>
  </button>

  {#if open}
    <textarea
      class="note-input"
      bind:value={draft}
      placeholder={$t('notes.placeholder')}
      oninput={onInput}
      onblur={commit}
      rows="4"
    ></textarea>
    {#if draft.trim() !== '' || existing}
      <div class="notes-foot">
        <button type="button" class="del" onclick={onDelete}>✕ {$t('notes.delete')}</button>
      </div>
    {/if}
  {/if}
</div>

<style>
  /* Matches .bio-block in the researcher detail page. */
  .notes-block {
    padding: 18px 28px;
    border-bottom: 1px solid var(--ink);
  }
  .notes-head {
    display: flex;
    width: 100%;
    align-items: center;
    justify-content: space-between;
    background: transparent;
    border: none;
    padding: 0;
    cursor: pointer;
  }
  .lbl-mini {
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--n500);
  }
  .head-right {
    display: inline-flex;
    align-items: center;
    gap: 10px;
  }
  .saved {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: var(--n500);
  }
  .caret {
    font-size: 11px;
    color: var(--n500);
  }
  /* Newspaper voice: same Lora italic as .bio-block p */
  .note-input {
    display: block;
    width: 100%;
    margin-top: 10px;
    padding: 10px 12px;
    background: var(--paper);
    border: 1px dashed var(--n400);
    font-family: 'Lora', serif;
    font-size: 15.5px;
    line-height: 1.65;
    font-style: italic;
    color: var(--n700);
    resize: vertical;
    min-height: 96px;
  }
  .note-input::placeholder {
    color: var(--n400);
    font-style: italic;
  }
  .note-input:focus {
    outline: none;
    border-color: var(--ink);
  }
  .notes-foot {
    display: flex;
    justify-content: flex-end;
    margin-top: 8px;
  }
  .del {
    background: transparent;
    border: 1px solid var(--n400);
    color: var(--n600);
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    padding: 2px 8px;
    cursor: pointer;
    line-height: 1.4;
  }
  .del:hover {
    border-color: var(--accent);
    color: var(--accent);
  }
</style>
