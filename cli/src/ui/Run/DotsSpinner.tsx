import React, { useState, useEffect } from 'react';
import { Text } from 'ink';
import { registerAnimationSubscriber } from '../animationTick.js';

const DOTS_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];

const DotsSpinner: React.FC = () => {
    const [frame, setFrame] = useState(0);

    useEffect(() => {
        const advance = () => setFrame(prev => (prev + 1) % DOTS_FRAMES.length);
        return registerAnimationSubscriber(advance);
    }, []);

    return <Text>{DOTS_FRAMES[frame]}</Text>;
};

export default DotsSpinner;
