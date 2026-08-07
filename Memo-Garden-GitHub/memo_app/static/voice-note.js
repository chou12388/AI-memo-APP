(() => {
    const content = document.getElementById('content');
    const title = document.getElementById('title');
    const dateInput = document.getElementById('date');
    const dateError = document.getElementById('date-error');
    const submitButton = document.getElementById('submit-btn');
    const memoVoiceButton = document.getElementById('memo-voice-button');
    const memoVoiceLanguage = document.getElementById('memo-voice-language');
    const memoVoiceStatus = document.getElementById('memo-voice-status');
    const contentCount = document.getElementById('content-count');
    const dialog = document.getElementById('ai-organizer-dialog');
    const openAiButton = document.getElementById('open-ai-popup');
    const closeAiButtons = [document.getElementById('close-ai-popup'), document.getElementById('close-ai-popup-secondary')];
    const aiInput = document.getElementById('ai-organizer-input');
    const aiCount = document.getElementById('ai-organizer-count');
    const aiVoiceButton = document.getElementById('ai-voice-button');
    const aiVoiceLanguage = document.getElementById('ai-voice-language');
    const aiVoiceStatus = document.getElementById('ai-voice-status');
    const aiRunButton = document.getElementById('run-ai-organizer');
    const aiStatus = document.getElementById('ai-organizer-status');
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const aiDraftKey = 'memo-garden-ai-organizer-draft';
    let memoRecognition, aiRecognition, memoListening = false, aiListening = false, aiAbortController;
    const aiModels = {
        gemini: [['gemini-3.6-flash', 'Gemini 3.6 Flash（無料枠あり）'], ['gemini-3.5-flash', 'Gemini 3.5 Flash（無料枠あり）'], ['gemini-3.5-flash-lite', 'Gemini 3.5 Flash-Lite（無料枠あり）'], ['gemini-2.5-flash', 'Gemini 2.5 Flash（無料枠あり）'], ['gemini-2.5-pro', 'Gemini 2.5 Pro（有料）']],
        openai: [['gpt-5.6-sol', 'GPT-5.6 Sol（有料）'], ['gpt-5.6-terra', 'GPT-5.6 Terra（有料）'], ['gpt-5.6-luna', 'GPT-5.6 Luna（有料）'], ['gpt-5.4-mini', 'GPT-5.4 mini（有料）'], ['gpt-5.4-nano', 'GPT-5.4 nano（有料）']],
        openrouter: [['openrouter/free', 'OpenRouter Free Router（無料）']],
        anthropic: [['claude-fable-5', 'Claude Fable 5（有料）'], ['claude-opus-5', 'Claude Opus 5（有料）'], ['claude-sonnet-5', 'Claude Sonnet 5（有料）'], ['claude-haiku-4-5-20251001', 'Claude Haiku 4.5（有料）']]
    };
    const settingsNotes = { gemini: 'Google の生成AIサービスです。無料 API 枠には回数・速度・日次の制限があります。', openai: 'OpenAI の生成AIサービスです。API の利用には残高が必要です。', openrouter: '複数の AI モデルをまとめて使えるサービスです。無料枠はテスト向けで、回数制限があります。', anthropic: 'Anthropic の生成AIサービスです。API の利用には残高が必要です。' };
    const settingsDialog = document.createElement('dialog');
    settingsDialog.className = 'api-key-dialog';
    settingsDialog.innerHTML = '<form class="ai-settings-form" id="local-ai-settings-form"><h2>AIモデルを選択</h2><p>このタブ内でのみ、選択したサービスの Key を記憶します。ブラウザのタブまたはブラウザを閉じると Key は削除されます。</p><div class="field"><label for="local-ai-provider">AIサービス</label><select class="voice-select" id="local-ai-provider"><option value="gemini">Google Gemini</option><option value="openai">OpenAI</option><option value="openrouter">OpenRouter</option><option value="anthropic">Anthropic Claude</option></select></div><p class="form-note" id="local-ai-note"></p><div class="field"><label for="local-ai-model">モデル</label><select class="voice-select" id="local-ai-model"></select></div><div class="field"><label for="local-ai-key">API Key</label><input type="password" id="local-ai-key" required autocomplete="off" placeholder="選択したサービスの API Key を入力"></div><div class="button-row"><button class="btn btn-primary" type="submit">保存する</button><button class="btn btn-secondary" id="cancel-local-ai-settings" type="button">キャンセル</button></div></form>';
    document.body.append(settingsDialog);
    const localProvider = settingsDialog.querySelector('#local-ai-provider');
    const localModel = settingsDialog.querySelector('#local-ai-model');
    const localKey = settingsDialog.querySelector('#local-ai-key');
    const localNote = settingsDialog.querySelector('#local-ai-note');
    let reopenOrganizerAfterSettings = false;
    const clearDialog = document.createElement('dialog');
    clearDialog.className = 'clear-confirm-dialog';
    clearDialog.innerHTML = '<div class="clear-confirm-card"><h2>入力内容をクリアしますか？</h2><p>この操作は元に戻せません。</p><div class="button-row"><button class="btn btn-danger" id="confirm-clear" type="button">クリアする</button><button class="btn btn-secondary" id="cancel-clear" type="button">キャンセル</button></div></div>';
    document.body.append(clearDialog);
    let pendingClearInput;

    const countCharacters = value => Array.from(value || '').length;
    const updateContentCount = () => { if (contentCount) contentCount.textContent = `${countCharacters(content.value)}文字`; };
    const updateAiCount = () => { if (aiCount) aiCount.textContent = `${countCharacters(aiInput.value)}文字`; };
    const setVoiceButton = (button, listening) => { if (!button) return; button.classList.toggle('recording', listening); button.textContent = listening ? '■ 音声入力を停止' : '🎙 音声で入力'; };
    const showAiDialog = () => { if (!dialog.open) dialog.showModal(); aiInput.focus(); };
    const saveAiDraft = () => sessionStorage.setItem(aiDraftKey, aiInput.value);
    const refreshLocalModels = () => { const choices = aiModels[localProvider.value]; localModel.replaceChildren(...choices.map(([value, label]) => new Option(label, value))); const saved = sessionStorage.getItem(`memo-garden-${localProvider.value}-model`); localModel.value = choices.some(([value]) => value === saved) ? saved : choices[0][0]; localKey.value = sessionStorage.getItem(`memo-garden-${localProvider.value}-key`) || ''; localNote.textContent = settingsNotes[localProvider.value]; };
    const openAiSettings = (returnToOrganizer = false) => { reopenOrganizerAfterSettings = returnToOrganizer; if (returnToOrganizer && dialog.open) dialog.close(); localProvider.value = sessionStorage.getItem('memo-garden-provider') || 'gemini'; refreshLocalModels(); settingsDialog.showModal(); localKey.focus(); };

    function appendVoiceToInput(input, languageSelect, button, status, onChange) {
        if (!SpeechRecognition) { status.textContent = 'このブラウザは音声認識に対応していません。Chrome または Edge をお試しください。'; return null; }
        const recognition = new SpeechRecognition();
        recognition.lang = languageSelect.value; recognition.interimResults = true; recognition.continuous = true;
        const base = input.value.trim(); let finalText = '';
        const display = text => { input.value = [base, text].filter(Boolean).join(base && text ? '\n' : ''); onChange(); };
        recognition.onresult = event => { let interim = ''; for (let i = event.resultIndex; i < event.results.length; i += 1) { if (event.results[i].isFinal) finalText += event.results[i][0].transcript; else interim += event.results[i][0].transcript; } display(finalText + interim); status.textContent = '音声認識中…'; };
        recognition.onerror = event => { status.textContent = event.error === 'not-allowed' ? 'マイクの使用を許可してください。' : `音声入力エラー: ${event.error}`; if (button === memoVoiceButton) memoListening = false; else aiListening = false; setVoiceButton(button, false); };
        recognition.onend = () => { if (button === memoVoiceButton && !memoListening) return; if (button === aiVoiceButton && !aiListening) return; if (button === memoVoiceButton) memoListening = false; else aiListening = false; display(finalText); setVoiceButton(button, false); status.textContent = finalText ? '音声認識の結果を編集できます。' : '音声を認識できませんでした。もう一度お試しください。'; };
        recognition.start(); return recognition;
    }

    memoVoiceButton?.addEventListener('click', () => {
        if (memoListening) { memoRecognition.stop(); return; }
        memoListening = true; setVoiceButton(memoVoiceButton, true); memoVoiceStatus.textContent = '音声入力中…話し終えたら停止してください';
        memoRecognition = appendVoiceToInput(content, memoVoiceLanguage, memoVoiceButton, memoVoiceStatus, updateContentCount);
        if (!memoRecognition) { memoListening = false; setVoiceButton(memoVoiceButton, false); }
    });

    aiVoiceButton?.addEventListener('click', () => {
        if (aiListening) { aiRecognition.stop(); return; }
        aiListening = true; setVoiceButton(aiVoiceButton, true); aiVoiceStatus.textContent = '音声入力中…話し終えたら停止してください';
        aiRecognition = appendVoiceToInput(aiInput, aiVoiceLanguage, aiVoiceButton, aiVoiceStatus, () => { updateAiCount(); saveAiDraft(); });
        if (!aiRecognition) { aiListening = false; setVoiceButton(aiVoiceButton, false); }
    });

    content?.addEventListener('input', updateContentCount);
    dateInput?.addEventListener('input', () => {
        const selected = new Date(dateInput.value); const today = new Date(); selected.setHours(0, 0, 0, 0); today.setHours(0, 0, 0, 0);
        const invalid = Boolean(dateInput.value) && selected < today;
        dateInput.classList.toggle('error-input', invalid); if (dateError) dateError.style.display = invalid ? 'block' : 'none'; if (submitButton) submitButton.disabled = invalid;
    });
    aiInput?.addEventListener('input', () => { updateAiCount(); saveAiDraft(); });
    document.querySelectorAll('[data-clear-target]').forEach(button => button.addEventListener('click', () => {
        const input = document.getElementById(button.dataset.clearTarget);
        if (!input) return;
        pendingClearInput = input; clearDialog.showModal();
    }));
    document.getElementById('confirm-clear').addEventListener('click', () => { if (pendingClearInput) { pendingClearInput.value = ''; pendingClearInput.dispatchEvent(new Event('input', { bubbles: true })); } pendingClearInput = undefined; clearDialog.close(); });
    document.getElementById('cancel-clear').addEventListener('click', () => { pendingClearInput = undefined; clearDialog.close(); });
    clearDialog.addEventListener('cancel', event => { event.preventDefault(); pendingClearInput = undefined; clearDialog.close(); });

    openAiButton?.addEventListener('click', showAiDialog);
    closeAiButtons.forEach(button => button?.addEventListener('click', () => dialog.close()));
    dialog?.addEventListener('cancel', event => { event.preventDefault(); dialog.close(); });
    document.querySelectorAll('a[href="/list#ai-settings"]').forEach(link => link.addEventListener('click', event => { event.preventDefault(); openAiSettings(); }));
    localProvider.addEventListener('change', refreshLocalModels);
    settingsDialog.querySelector('#local-ai-settings-form').addEventListener('submit', event => { event.preventDefault(); const key = localKey.value.trim(); if (!key) return; sessionStorage.setItem('memo-garden-provider', localProvider.value); sessionStorage.setItem(`memo-garden-${localProvider.value}-model`, localModel.value); sessionStorage.setItem(`memo-garden-${localProvider.value}-key`, key); settingsDialog.close(); if (reopenOrganizerAfterSettings) { reopenOrganizerAfterSettings = false; showAiDialog(); } });
    const closeLocalSettings = () => { settingsDialog.close(); if (reopenOrganizerAfterSettings) { reopenOrganizerAfterSettings = false; showAiDialog(); } };
    settingsDialog.querySelector('#cancel-local-ai-settings').addEventListener('click', closeLocalSettings);
    settingsDialog.addEventListener('cancel', event => { event.preventDefault(); closeLocalSettings(); });

    aiRunButton?.addEventListener('click', async () => {
        if (aiAbortController) { aiAbortController.abort(); return; }
        const transcript = aiInput.value.trim();
        const provider = sessionStorage.getItem('memo-garden-provider') || '';
        const model = sessionStorage.getItem(`memo-garden-${provider}-model`) || '';
        const apiKey = sessionStorage.getItem(`memo-garden-${provider}-key`) || '';
        if (!transcript) { aiStatus.textContent = '入力内容を入力してください。'; return; }
        if (!provider || !model || !apiKey) { openAiSettings(true); return; }
        aiAbortController = new AbortController(); aiRunButton.textContent = '■ AI 整理を中断'; aiStatus.textContent = 'AI が整理しています…';
        try {
            const data = new FormData();
            data.append('transcript', transcript); data.append('language', aiVoiceLanguage.value);
            data.append('provider', provider); data.append('model', model); data.append('api_key', apiKey);
            const response = await fetch('/voice_note', { method: 'POST', body: data, signal: aiAbortController.signal });
            const draft = await response.json(); if (!response.ok) throw new Error(draft.error || 'AI による整理に失敗しました。');
            title.value = draft.title; document.getElementById('date').value = draft.date; content.value = draft.content; updateContentCount(); aiStatus.textContent = '主画面へ入力しました。';
            setTimeout(() => dialog.close(), 500);
        } catch (error) { aiStatus.textContent = error.name === 'AbortError' ? 'AI 整理を中断しました。' : (error.message || 'AI による整理に失敗しました。'); }
        finally { aiAbortController = undefined; aiRunButton.textContent = '✦ AIで整理する'; }
    });

    aiInput.value = sessionStorage.getItem(aiDraftKey) || ''; updateContentCount(); updateAiCount();
})();
